"""
CiscoAuth: ciclo de vida do access_token OAuth2 (client_credentials).

- Credenciais vão em header Basic (nunca em query string).
- Token só em memória; renovado automaticamente antes de expirar (margem 60s).
- Nunca é logado nem devolvido em respostas de tool MCP.
"""
from __future__ import annotations

import base64
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
    expires_at: float

    def is_expired(self) -> bool:
        return time.time() >= (self.expires_at - _EXPIRY_SAFETY_MARGIN_SECONDS)


class CiscoAuthError(RuntimeError):
    pass


class CiscoAuth:
    def __init__(self, settings: Settings, http_client: Optional[httpx.Client] = None):
        self._settings = settings
        self._http = http_client or httpx.Client(timeout=settings.http_timeout_seconds)
        self._token: Optional[_Token] = None

    def _fetch_token(self) -> _Token:
        basic = base64.b64encode(
            f"{self._settings.cisco_client_id}:{self._settings.cisco_client_secret.get_secret_value()}".encode()
        ).decode()

        start = time.monotonic()
        try:
            resp = self._http.post(
                self._settings.cisco_token_url,
                data={"grant_type": "client_credentials"},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Basic {basic}",
                },
            )
        except httpx.HTTPError as exc:
            log_event("token_request_failed", endpoint=self._settings.cisco_token_url, error=str(exc))
            raise CiscoAuthError(f"Falha de rede ao obter token Cisco: {exc}") from exc

        log_event(
            "token_request",
            endpoint=self._settings.cisco_token_url,
            http_status=resp.status_code,
            duration_ms=round((time.monotonic() - start) * 1000, 1),
        )

        if resp.status_code != 200:
            raise CiscoAuthError(
                f"Cisco OAuth retornou HTTP {resp.status_code} ao solicitar token "
                f"(client_credentials). Verifique CISCO_CLIENT_ID, CISCO_CLIENT_SECRET e CISCO_TOKEN_URL."
            )

        body = resp.json()
        access_token = body.get("access_token")
        if not access_token:
            raise CiscoAuthError("Resposta de token Cisco sem access_token.")
        return _Token(value=access_token, expires_at=time.time() + float(body.get("expires_in", 3600)))

    def _ensure_token(self) -> _Token:
        if self._token is None or self._token.is_expired():
            self._token = self._fetch_token()
        return self._token

    def auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._ensure_token().value}"}

    def force_refresh(self) -> dict[str, str]:
        self._token = self._fetch_token()
        return {"Authorization": f"Bearer {self._token.value}"}
