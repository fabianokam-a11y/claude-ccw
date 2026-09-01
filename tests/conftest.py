import os

import pytest

os.environ.setdefault("CISCO_CLIENT_ID", "test-client-id")
os.environ.setdefault("CISCO_CLIENT_SECRET", "test-secret")
os.environ.setdefault("CISCO_TOKEN_URL", "https://cloudsso.cisco.com/as/token.oauth2")
os.environ.setdefault("CISCO_API_BASE_URL", "https://api.cisco.com")
os.environ.setdefault("CISCO_COMMERCE_BASE_URL", "https://apix.cisco.com")
os.environ.setdefault("CCW_DRY_RUN", "true")

from app.config import Settings  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]
