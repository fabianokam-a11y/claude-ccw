if __name__ == "__main__":
    if settings.mcp_transport == "streamable-http":
        # Servidor remoto: expõe HTTP e exige Bearer token em toda requisição,
        # exceto /healthz (usada pelo Render para saber se o serviço está de pé).
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
        mcp.run()  # stdio — uso local com Claude Desktop
