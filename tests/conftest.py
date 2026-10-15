import os

import pytest

os.environ.setdefault("CISCO_CLIENT_ID", "test-client-id")
os.environ.setdefault("CISCO_CLIENT_SECRET", "test-secret")
os.environ.setdefault("CISCO_TOKEN_URL", "https://id.cisco.com/oauth2/default/v1/token")
os.environ.setdefault("CCW_DRY_RUN", "true")

from app.config import Settings  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    s.http_backoff_base_seconds = 0.01
    return s
