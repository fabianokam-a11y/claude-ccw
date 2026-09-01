"""
CiscoAuth: gerencia o ciclo de vida do access_token OAuth2 da Cisco.

- Suporta grant_type=client_credentials (padrão/recomendado) e
  grant_type=password (Resource Owner, necessário se a Estimate API
  exigir contexto de usuário CCW).
- Token fica somente em memória (nunca em disco, nunca em log).
- Renova automaticamente antes de expirar (margem de 60s).
- Nunca é serializado em uma resposta de tool MCP.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import Settings
from app.logging_setup import log_event

_EXPIRY_SAFETY_MARGIN_SECONDS = 60


@dataclass
class _Token:
    value: str
    expires_at: float  # epoch seconds

    def is_expired(self) -> bool:
        return time.time() >= (self.expires_at - _EXPIRY_SAFETY_MARGIN_SECONDS)


class CiscoAuthError(RuntimeError):
    pass


class CiscoAuth:
    """Responsável exclusivamente por obter/renovar o access_token.

    O token NUNCA é retornado por métodos públicos usados fora desta
    classe/clients HTTP internos — apenas o header Authorization é
    construído internamente via `auth_header()`.
    """

    def __init__(self, settings: Settings, http_client: Optional[httpx.Client] = None):
        self._settings = settings
        self._http = http_client or httpx.Client(timeout=settings.http_timeout_seconds)
        self._token: Optional[_Token] = None

    def _fetch_token(self) -> _Token:
        data = {
            "grant_type": self._settings.cisco_grant_type,
            "client_id": self._settings.cisco_client_id,
            "client_secret": self._settings.cisco_client_secret.get_secret_value(),
        }
        if self._settings.cisco_grant_type == "password":
            data["username"] = self._settings.cisco_cco_username or ""
            data["password"] = (
                self._settings.cisco_cco_password.get_secret_value()
                if self._settings.cisco_cco_password
                else ""
            )

        start = time.monotonic()
        try:
            # A doc oficial da Cisco mostra client_id/client_secret como
            # query params na URL (além do form body) — mandamos os dois
            # jeitos pra máxima compatibilidade com o comportamento real
            # do servidor de token deles.
            resp = self._http.post(
                self._settings.cisco_token_url,
                params=data,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as exc:
            log_event("token_request_failed", endpoint=self._settings.cisco_token_url, error=str(exc))
            raise CiscoAuthError(f"Falha de rede ao obter token Cisco: {exc}") from exc

        duration_ms = (time.monotonic() - start) * 1000
        log_event(
            "token_request",
            endpoint=self._settings.cisco_token_url,
            http_status=resp.status_code,
            duration_ms=round(duration_ms, 1),
        )

        if resp.status_code != 200:
            # Nunca logar o corpo cru (pode ecoar client_id/erro sensível em alguns casos),
            # mas o status/erro estruturado é seguro.
            raise CiscoAuthError(
                f"Cisco OAuth retornou HTTP {resp.status_code} ao solicitar token "
                f"(grant_type={self._settings.cisco_grant_type}). Verifique client_id/secret "
                f"e se o grant_type é o suportado pela API."
            )

        body = resp.json()
        access_token = body.get("access_token")
        expires_in = float(body.get("expires_in", 3600))
        if not access_token:
            raise CiscoAuthError("Resposta de token Cisco sem access_token.")

        return _Token(value=access_token, expires_at=time.time() + expires_in)

    def _ensure_token(self) -> _Token:
        if self._token is None or self._token.is_expired():
            self._token = self._fetch_token()
        return self._token

    def auth_header(self) -> dict[str, str]:
        """Retorna apenas o header pronto para uso — nunca o token cru."""
        token = self._ensure_token()
        return {"Authorization": f"Bearer {token.value}"}

    def force_refresh(self) -> dict[str, str]:
        """Usado pelos clients HTTP ao receber 401 — renova e tenta 1x."""
        self._token = self._fetch_token()
        return {"Authorization": f"Bearer {self._token.value}"}
