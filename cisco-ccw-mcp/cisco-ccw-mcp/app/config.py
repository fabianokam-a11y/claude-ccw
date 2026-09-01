"""
Configuração central da aplicação.

Todas as credenciais e URLs vêm exclusivamente de variáveis de ambiente
(carregadas de um arquivo .env local, ou das env vars do painel do Render
em produção). Nada de segredo é hardcoded aqui.

Regra de ouro: nenhum campo sensível (client_secret, cco_password,
refresh_token, mcp_access_token) deve ser logado ou retornado em respostas
de tools MCP.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OAuth
    cisco_client_id: str = Field(...)
    cisco_client_secret: SecretStr = Field(...)
    cisco_grant_type: Literal["client_credentials", "password"] = "client_credentials"
    cisco_token_url: str = Field(...)

    # APIs
    cisco_api_base_url: str = Field(...)
    cisco_commerce_base_url: str = Field(...)

    # Somente necessário se grant_type == password
    cisco_cco_username: Optional[str] = None
    cisco_cco_password: Optional[SecretStr] = None

    # Authorization Code (fallback, se algum dia necessário)
    cisco_redirect_uri: Optional[str] = None
    cisco_refresh_token: Optional[SecretStr] = None

    # Comportamento
    ccw_dry_run: bool = True
    default_currency: str = "USD"
    log_level: str = "INFO"

    # HTTP (chamadas para a Cisco)
    http_timeout_seconds: float = 20.0
    http_max_retries: int = 3
    http_backoff_base_seconds: float = 1.5

    # --- Servidor MCP em si ---
    # "stdio" (padrão, Claude Desktop local) ou "streamable-http" (deploy
    # remoto tipo Render, para virar Custom Connector no claude.ai)
    mcp_transport: Literal["stdio", "streamable-http"] = "stdio"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000
    # Token que o claude.ai deve enviar como "Authorization: Bearer <token>".
    # Gere algo forte, ex: python -c "import secrets; print(secrets.token_urlsafe(32))"
    # Obrigatório apenas quando mcp_transport == streamable-http.
    mcp_access_token: Optional[SecretStr] = None

    def validate_grant_requirements(self) -> None:
        if self.cisco_grant_type == "password":
            if not self.cisco_cco_username or not self.cisco_cco_password:
                raise ValueError(
                    "CISCO_GRANT_TYPE=password exige CISCO_CCO_USERNAME e "
                    "CISCO_CCO_PASSWORD no .env"
                )
        if self.mcp_transport == "streamable-http" and not self.mcp_access_token:
            raise ValueError(
                "MCP_TRANSPORT=streamable-http exige MCP_ACCESS_TOKEN definido — "
                "sem isso, o servidor ficaria público sem autenticação para "
                "qualquer pessoa que descobrir a URL do Render."
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()  # type: ignore[call-arg]
    # Render (e a maioria dos PaaS) injeta a porta via $PORT, não $MCP_PORT.
    # Prioriza $PORT quando presente, sem exigir que o usuário duplique a
    # variável no .env local.
    render_port = os.environ.get("PORT")
    if render_port:
        settings.mcp_port = int(render_port)
    settings.validate_grant_requirements()
    return settings
