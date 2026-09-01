"""
Servidor MCP - Cisco Commerce / CCW.

Expõe 12 tools ao Claude:
  search_cisco_product, get_cisco_product, get_cisco_list_price,
  get_cisco_prices, create_ccw_estimate, get_ccw_estimate,
  list_ccw_estimates, add_item_to_ccw_estimate, update_ccw_estimate_item,
  remove_ccw_estimate_item, delete_ccw_estimate, duplicate_ccw_estimate

Dois modos de execução, controlados pela env var MCP_TRANSPORT:

  - "stdio" (padrão): uso local com Claude Desktop.
        python -m app.main
  - "streamable-http": uso remoto, como Custom Connector no claude.ai.
    Sobe um servidor HTTP na porta $PORT (Render injeta isso automaticamente).
        MCP_TRANSPORT=streamable-http python -m app.main
"""
from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from app.auth import CiscoAuth
from app.clients.catalog import CiscoCatalogClient
from app.clients.commerce import CiscoApiError, CiscoBaseClient
from app.clients.estimates import CiscoEstimateClient
from app.config import get_settings
from app.logging_setup import log_event
from app.tools import estimates as estimate_tools
from app.tools import pricing as pricing_tools
from app.tools import products as product_tools

settings = get_settings()
_auth = CiscoAuth(settings)
_base = CiscoBaseClient(settings, _auth)
_catalog = CiscoCatalogClient(_base, settings.cisco_api_base_url, settings.default_currency)
_estimate_client = CiscoEstimateClient(_base, settings)

mcp = FastMCP("cisco-ccw-mcp", stateless_http=True)


def _wrap(fn, *args, **kwargs) -> dict:
    """Padroniza tratamento de erro para todas as tools: nunca deixa
    exceção crua vazar (poderia conter detalhes de payload) e nunca
    inclui token/segredo na resposta."""
    try:
        return fn(*args, **kwargs)
    except CiscoApiError as exc:
        log_event("tool_error", tool=fn.__name__, http_status=exc.status_code, error=str(exc))
        return {"error": str(exc), "status_code": exc.status_code, "details": exc.details}
    except Exception as exc:  # noqa: BLE001
        log_event("tool_error_unexpected", tool=fn.__name__, error=str(exc))
        return {"error": f"Erro inesperado em {fn.__name__}: {exc}"}


# ---------- Catálogo / Preço ----------


@mcp.tool()
def search_cisco_product(query: str) -> dict:
    """Pesquisa SKUs Cisco por texto livre e retorna produtos correspondentes."""
    return _wrap(product_tools.search_cisco_product, _catalog, query)


@mcp.tool()
def get_cisco_product(sku: str) -> dict:
    """Retorna todas as informações disponíveis sobre um SKU Cisco específico."""
    return _wrap(product_tools.get_cisco_product, _catalog, sku)


@mcp.tool()
def get_cisco_list_price(sku: str, quantity: int = 1) -> dict:
    """Retorna o GPL (List Price) Cisco de um SKU para a quantidade informada,
    já com o total calculado."""
    return _wrap(pricing_tools.get_cisco_list_price, _catalog, sku, quantity)


@mcp.tool()
def get_cisco_prices(items: list[dict]) -> dict:
    """Consulta preços de vários SKUs de uma vez. items: [{"sku": str, "quantity": int}, ...]."""
    return _wrap(pricing_tools.get_cisco_prices, _catalog, items)


# ---------- Estimates ----------


@mcp.tool()
def create_ccw_estimate(name: str, items: list[dict], confirm: bool = False) -> dict:
    """Cria um Estimate no CCW. NÃO chame com confirm=True sem antes mostrar
    o resumo (SKUs, quantidades, GPL total) ao usuário e obter confirmação
    explícita dele. Chame primeiro com confirm=False para obter o preview."""
    return _wrap(estimate_tools.create_ccw_estimate, _estimate_client, name, items, confirm)


@mcp.tool()
def get_ccw_estimate(estimate_id: str) -> dict:
    """Consulta um Estimate existente no CCW por ID."""
    return _wrap(estimate_tools.get_ccw_estimate, _estimate_client, estimate_id)


@mcp.tool()
def list_ccw_estimates(
    limit: Optional[int] = None,
    status: Optional[str] = None,
    created_after: Optional[str] = None,
    search: Optional[str] = None,
) -> dict:
    """Lista Estimates do usuário, com filtros opcionais."""
    return _wrap(estimate_tools.list_ccw_estimates, _estimate_client, limit, status, created_after, search)


@mcp.tool()
def add_item_to_ccw_estimate(estimate_id: str, sku: str, quantity: int, confirm: bool = False) -> dict:
    """Adiciona um item a um Estimate existente. Exige confirmação explícita do usuário."""
    return _wrap(estimate_tools.add_item_to_ccw_estimate, _estimate_client, estimate_id, sku, quantity, confirm)


@mcp.tool()
def update_ccw_estimate_item(estimate_id: str, sku: str, quantity: int, confirm: bool = False) -> dict:
    """Atualiza a quantidade de um item em um Estimate. Exige confirmação explícita."""
    return _wrap(estimate_tools.update_ccw_estimate_item, _estimate_client, estimate_id, sku, quantity, confirm)


@mcp.tool()
def remove_ccw_estimate_item(estimate_id: str, sku: str, confirm: bool = False) -> dict:
    """Remove um item de um Estimate. Exige confirmação explícita."""
    return _wrap(estimate_tools.remove_ccw_estimate_item, _estimate_client, estimate_id, sku, confirm)


@mcp.tool()
def delete_ccw_estimate(estimate_id: str, confirm: bool = False) -> dict:
    """Exclui um Estimate. NUNCA excluir sem confirmação explícita do usuário."""
    return _wrap(estimate_tools.delete_ccw_estimate, _estimate_client, estimate_id, confirm)


@mcp.tool()
def duplicate_ccw_estimate(estimate_id: str, new_name: str, confirm: bool = False) -> dict:
    """Duplica um Estimate existente com um novo nome."""
    return _wrap(estimate_tools.duplicate_ccw_estimate, _estimate_client, estimate_id, new_name, confirm)


if __name__ == "__main__":
    if settings.mcp_transport == "streamable-http":
        # Servidor remoto: expõe HTTP e exige Bearer token em toda requisição.
        import uvicorn

        from app.http_auth import BearerAuthMiddleware

        app = mcp.streamable_http_app()
        app.add_middleware(
            BearerAuthMiddleware,
            expected_token=settings.mcp_access_token.get_secret_value(),  # type: ignore[union-attr]
        )
        log_event("mcp_server_starting", endpoint=f"{settings.mcp_host}:{settings.mcp_port}")
        uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)
    else:
        mcp.run()  # stdio — uso local com Claude Desktop
