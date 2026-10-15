"""
Servidor MCP - Cisco Commerce / CCW (API GraphQL).

Tools expostas ao Claude:
  get_cisco_list_price, get_cisco_prices            (preço de lista, somente leitura)
  search_ccw_estimates, get_ccw_estimate, validate_ccw_estimate   (leitura)
  create_ccw_estimate, add_item_to_ccw_estimate, update_ccw_estimate_item,
  remove_ccw_estimate_item, share_ccw_estimate      (escrita, com confirmação)

Não existem (a API não libera): busca de catálogo, excluir e duplicar estimate.

Modos (env MCP_TRANSPORT): "stdio" (Claude Desktop local) ou "streamable-http"
(Custom Connector no claude.ai, ex.: Render; porta vem de $PORT).
"""
from __future__ import annotations

import os
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.auth import CiscoAuth
from app.clients.catalog import CiscoCatalogClient
from app.clients.commerce import CiscoApiError, CiscoBaseClient
from app.clients.estimates import CiscoEstimateClient
from app.config import get_settings
from app.logging_setup import log_event
from app.tools import estimates as estimate_tools
from app.tools import pricing as pricing_tools

settings = get_settings()
_auth = CiscoAuth(settings)
_base = CiscoBaseClient(settings, _auth)
_catalog = CiscoCatalogClient(_base, settings)
_estimates = CiscoEstimateClient(_base, settings)

# Proteção contra DNS rebinding do SDK do MCP: libera o hostname público do
# serviço (Render injeta RENDER_EXTERNAL_HOSTNAME; MCP_PUBLIC_HOSTNAME é fallback).
_public_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME") or os.environ.get("MCP_PUBLIC_HOSTNAME")
_allowed_hosts = ["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*"]
_allowed_origins = ["http://127.0.0.1:*", "http://localhost:*"]
if _public_hostname:
    _allowed_hosts.append(_public_hostname)
    _allowed_origins.append(f"https://{_public_hostname}")

mcp = FastMCP(
    "cisco-ccw-mcp",
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_allowed_hosts,
        allowed_origins=_allowed_origins,
    ),
)


def _wrap(fn, *args, **kwargs) -> dict:
    """Erros viram resposta legível; nunca vaza token/segredo."""
    try:
        return fn(*args, **kwargs)
    except CiscoApiError as exc:
        log_event("tool_error", tool=fn.__name__, http_status=exc.status_code, error=str(exc))
        return {"error": str(exc), "status_code": exc.status_code}
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        log_event("tool_error_unexpected", tool=fn.__name__, error=str(exc))
        return {"error": f"Erro inesperado em {fn.__name__}: {exc}"}


# ---------- Preço de lista (somente leitura, não cria estimate) ----------


@mcp.tool()
def get_cisco_list_price(sku: str, quantity: float = 1, price_list: Optional[str] = None) -> dict:
    """Preço de lista (GPL / List Price) Cisco de um SKU, com total para a quantidade.
    price_list: GLBRL = Brasil (BRL, padrão); GLICON = LATAM (USD, inclui Meraki); GLUS = US (USD).
    Se o SKU não vier com preço no GLBRL, tente GLUS ou GLICON. Sempre informe ao usuário que é
    preço de LISTA (GPL), não preço líquido."""
    return _wrap(pricing_tools.get_cisco_list_price, _catalog, sku, quantity, price_list)


@mcp.tool()
def get_cisco_prices(items: list[dict], price_list: Optional[str] = None) -> dict:
    """Preço de lista de vários SKUs em UMA chamada. items: [{"sku": str, "quantity": number}, ...].
    Devolve cada linha, total por linha e grand_total (GPL, não líquido)."""
    return _wrap(pricing_tools.get_cisco_prices, _catalog, items, price_list)


# ---------- Estimates: leitura ----------


@mcp.tool()
def search_ccw_estimates(name: str) -> dict:
    """Busca estimates por trecho do NOME (ex.: ID da proposta). Só enxerga estimates
    compartilhados com o usuário da API. Não busca por ID de estimate nem por status."""
    return _wrap(estimate_tools.search_ccw_estimates, _estimates, name)


@mcp.tool()
def get_ccw_estimate(estimate_id: str) -> dict:
    """Linhas (SKU, qtd, lista, desconto, líquido), total e price list de um estimate.
    Só lê estimates compartilhados com o usuário da API."""
    return _wrap(estimate_tools.get_ccw_estimate, _estimates, estimate_id)


@mcp.tool()
def validate_ccw_estimate(estimate_id: str) -> dict:
    """Roda a validação do CCW e devolve status atual e mensagens de erro/aviso de configuração.
    O validador devolve 1 erro por chamada em alguns casos; pode ser preciso repetir."""
    return _wrap(estimate_tools.validate_ccw_estimate, _estimates, estimate_id)


# ---------- Estimates: escrita (exigem confirmação) ----------


@mcp.tool()
def create_ccw_estimate(
    name: str, items: list[dict], price_list: Optional[str] = None, confirm: bool = False
) -> dict:
    """Cria um estimate no CCW. items: [{"sku", "quantity", "parent" (índice 1-based, 0=raiz),
    "duration_months" (obrigatório p/ serviço/subscrição)}]. A price list não muda depois de criada.
    Chame primeiro com confirm=False (preview), mostre o resumo ao usuário e SÓ chame com
    confirm=True após confirmação explícita. Nome padrão: BoM_BR_ID<id> <Cliente>- <descrição>_rev<n>."""
    return _wrap(estimate_tools.create_ccw_estimate, _estimates, name, items, price_list, confirm)


@mcp.tool()
def add_item_to_ccw_estimate(
    estimate_id: str, sku: str, quantity: float, parent: int = 0,
    duration_months: Optional[int] = None, confirm: bool = False,
) -> dict:
    """Adiciona um item. ATENÇÃO: o update reenvia todas as linhas e NÃO reprecifica
    (pode ficar UNVERIFIED, serviços a 0). Exige confirmação explícita (confirm=True)."""
    return _wrap(estimate_tools.add_item_to_ccw_estimate, _estimates, estimate_id, sku, quantity,
                 parent, duration_months, confirm)


@mcp.tool()
def update_ccw_estimate_item(estimate_id: str, sku: str, quantity: float, confirm: bool = False) -> dict:
    """Altera a quantidade de um SKU. Mesmo aviso de não reprecificar. Exige confirm=True."""
    return _wrap(estimate_tools.update_ccw_estimate_item, _estimates, estimate_id, sku, quantity, confirm)


@mcp.tool()
def remove_ccw_estimate_item(estimate_id: str, sku: str, confirm: bool = False) -> dict:
    """Remove um SKU (filhos sobem para o avô). Mesmo aviso de não reprecificar. Exige confirm=True."""
    return _wrap(estimate_tools.remove_ccw_estimate_item, _estimates, estimate_id, sku, confirm)


@mcp.tool()
def share_ccw_estimate(estimate_id: str, emails: Optional[list[str]] = None, confirm: bool = False) -> dict:
    """Compartilha o estimate (READ_WRITE) com os e-mails informados (ou CCW_SHARE_EMAILS).
    Necessário para o usuário abrir no CCW um estimate criado pela API. Exige confirm=True."""
    return _wrap(estimate_tools.share_ccw_estimate, _estimates, estimate_id, emails, confirm)


if __name__ == "__main__":
    if settings.mcp_transport == "streamable-http":
        import uvicorn
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route

        from app.http_auth import BearerAuthMiddleware

        async def healthz(request):
            return PlainTextResponse("ok")

        app = mcp.streamable_http_app()
        app.router.routes.append(Route("/healthz", healthz, methods=["GET"]))
        app.add_middleware(
            BearerAuthMiddleware,
            expected_token=settings.mcp_access_token.get_secret_value(),  # type: ignore[union-attr]
            public_paths=("/healthz",),
        )
        log_event("mcp_server_starting", endpoint=f"{settings.mcp_host}:{settings.mcp_port}")
        uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)
    else:
        mcp.run()
