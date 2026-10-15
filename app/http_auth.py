"""
Middleware ASGI: exige "Authorization: Bearer <MCP_ACCESS_TOKEN>" em toda
requisição ao servidor MCP remoto, exceto nos caminhos públicos (health check).
Comparação em tempo constante (hmac.compare_digest).
"""
from __future__ import annotations

import hmac

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.logging_setup import log_event


class BearerAuthMiddleware:
    def __init__(self, app: ASGIApp, expected_token: str, public_paths: tuple[str, ...] = ()):
        self._app = app
        self._expected_token = expected_token
        self._public_paths = public_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        if scope.get("path") in self._public_paths:
            await self._app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()
        provided = auth_header[len("Bearer "):] if auth_header.startswith("Bearer ") else ""

        if not provided or not hmac.compare_digest(provided, self._expected_token):
            log_event("unauthorized_http_request", endpoint=str(scope.get("path")))
            await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
            return

        await self._app(scope, receive, send)
