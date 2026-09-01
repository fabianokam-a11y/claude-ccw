import time

import httpx
import respx

from app.auth import CiscoAuth, CiscoAuthError

TOKEN_URL = "https://cloudsso.cisco.com/as/token.oauth2"


@respx.mock
def test_fetches_token_and_caches(settings):
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "abc123", "expires_in": 3600})
    )
    auth = CiscoAuth(settings)
    header1 = auth.auth_header()
    header2 = auth.auth_header()

    assert header1 == {"Authorization": "Bearer abc123"}
    assert header2 == header1
    assert route.call_count == 1  # segunda chamada usa cache, não bate na rede


@respx.mock
def test_token_never_leaks_client_secret_in_return(settings):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "abc123", "expires_in": 3600}))
    auth = CiscoAuth(settings)
    header = auth.auth_header()
    assert "test-secret" not in str(header)


@respx.mock
def test_refetches_when_expired(settings):
    route = respx.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "first", "expires_in": 1}),
            httpx.Response(200, json={"access_token": "second", "expires_in": 3600}),
        ]
    )
    auth = CiscoAuth(settings)
    first = auth.auth_header()
    time.sleep(1.1)
    second = auth.auth_header()

    assert first != second
    assert route.call_count == 2


@respx.mock
def test_token_error_raises_clean_exception(settings):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(401, json={"error": "invalid_client"}))
    auth = CiscoAuth(settings)
    try:
        auth.auth_header()
        assert False, "deveria ter levantado CiscoAuthError"
    except CiscoAuthError as exc:
        assert "test-secret" not in str(exc)
