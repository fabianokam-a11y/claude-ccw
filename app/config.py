"""
Configuração central. Tudo vem de variáveis de ambiente (.env local ou painel
do Render). Nenhum segredo é hardcoded, logado ou devolvido por tools MCP.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OAuth Cisco (client_credentials)
    cisco_client_id: str = Field(...)
    cisco_client_secret: SecretStr = Field(...)
    cisco_token_url: str = "https://id.cisco.com/oauth2/default/v1/token"

    # API GraphQL do Cisco Commerce (CCW Estimate), PROD
    ccw_graphql_url: str = "https://capi.cisco.com/commerce/apis"

    # Comportamento
    ccw_dry_run: bool = True
    # Price list padrão: GLBRL = Brasil (BRL); GLICON = LATAM (USD, Meraki); GLUS = US (USD)
    ccw_default_price_list: str = "GLBRL"
    # E-mails (separados por vírgula) que recebem READ_WRITE em todo estimate criado pela API
    ccw_share_emails: str = ""
    log_level: str = "INFO"

    # HTTP (chamadas para a Cisco)
    http_timeout_seconds: float = 30.0
    http_max_retries: int = 3
    http_backoff_base_seconds: float = 1.5

    # Servidor MCP em si
    mcp_transport: Literal["stdio", "streamable-http"] = "stdio"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000
    mcp_access_token: Optional[SecretStr] = None

    def share_emails(self) -> list[str]:
        return [e.strip() for e in self.ccw_share_emails.split(",") if e.strip()]

    def validate_requirements(self) -> None:
        if self.mcp_transport == "streamable-http" and not self.mcp_access_token:
            raise ValueError(
                "MCP_TRANSPORT=streamable-http exige MCP_ACCESS_TOKEN definido — "
                "sem isso o servidor ficaria público sem autenticação."
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()  # type: ignore[call-arg]
    render_port = os.environ.get("PORT")
    if render_port:
        settings.mcp_port = int(render_port)
    settings.validate_requirements()
    return settings
