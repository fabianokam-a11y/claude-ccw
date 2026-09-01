"""
Middleware ASGI simples: exige "Authorization: Bearer <token>" em toda
requisição quando o servidor roda em modo remoto (streamable-http).

Isso é o que impede que qualquer pessoa que descubra a URL pública do
servidor consiga chamar as tools (inclusive as de escrita no CCW).
O token é comparado com hmac.compare_digest para evitar timing attack.
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
            # Rota de health check do Render — precisa responder sem token,
            # senão o Render marca o deploy como "não saudável" e derruba o
            # serviço mesmo com o servidor rodando perfeitamente.
            await self._app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()

        provided = ""
        if auth_header.startswith("Bearer "):
            provided = auth_header[len("Bearer ") :]

        if not provided or not hmac.compare_digest(provided, self._expected_token):
            log_event("unauthorized_http_request", endpoint=str(scope.get("path")))
            response = JSONResponse({"error": "unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)
