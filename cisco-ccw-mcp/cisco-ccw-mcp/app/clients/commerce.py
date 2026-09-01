"""
Client HTTP base compartilhado por CiscoCatalogClient e CiscoEstimateClient.

Responsabilidades:
- Anexar o header Authorization via CiscoAuth (nunca expõe o token).
- Repetir a requisição 1x se receber 401 (renovando o token).
- Retry com backoff exponencial para 429 e 5xx.
- Timeout configurável.
- Logar cada chamada (sem dados sensíveis).
"""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from app.auth import CiscoAuth
from app.config import Settings
from app.logging_setup import log_event


class CiscoApiError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class CiscoBaseClient:
    def __init__(self, settings: Settings, auth: CiscoAuth, http_client: Optional[httpx.Client] = None):
        self._settings = settings
        self._auth = auth
        self._http = http_client or httpx.Client(timeout=settings.http_timeout_seconds)

    def request(
        self,
        method: str,
        url: str,
        *,
        tool: str,
        json_body: Optional[dict] = None,
        content: Optional[str] = None,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> httpx.Response:
        headers = dict(headers or {})
        headers.update(self._auth.auth_header())

        attempt = 0
        used_401_retry = False
        max_retries = self._settings.http_max_retries

        while True:
            attempt += 1
            start = time.monotonic()
            try:
                resp = self._http.request(
                    method,
                    url,
                    json=json_body,
                    content=content,
                    headers=headers,
                    params=params,
                )
            except httpx.HTTPError as exc:
                if attempt > max_retries:
                    log_event("http_request_failed", tool=tool, endpoint=url, error=str(exc))
                    raise CiscoApiError(f"Falha de rede após {attempt} tentativas: {exc}") from exc
                self._backoff(attempt)
                continue

            duration_ms = (time.monotonic() - start) * 1000
            log_event(
                "http_request",
                tool=tool,
                endpoint=url,
                http_status=resp.status_code,
                duration_ms=round(duration_ms, 1),
                attempt=attempt,
            )

            if resp.status_code == 401 and not used_401_retry:
                # Renova token uma única vez e repete a chamada
                used_401_retry = True
                headers.update(self._auth.force_refresh())
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt > max_retries:
                    raise CiscoApiError(
                        f"Cisco API retornou HTTP {resp.status_code} após {attempt} tentativas.",
                        status_code=resp.status_code,
                    )
                self._backoff(attempt, retry_after=resp.headers.get("Retry-After"))
                continue

            if resp.status_code >= 400:
                raise CiscoApiError(
                    f"Cisco API retornou HTTP {resp.status_code}.",
                    status_code=resp.status_code,
                    details=self._safe_body(resp),
                )

            return resp

    def _backoff(self, attempt: int, retry_after: Optional[str] = None) -> None:
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = self._settings.http_backoff_base_seconds * (2 ** (attempt - 1))
        else:
            delay = self._settings.http_backoff_base_seconds * (2 ** (attempt - 1))
        time.sleep(min(delay, 30))

    @staticmethod
    def _safe_body(resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except Exception:
            return resp.text[:1000]
