import httpx
import respx

from app.auth import CiscoAuth
from app.clients.commerce import CiscoApiError, CiscoBaseClient

TOKEN_URL = "https://cloudsso.cisco.com/as/token.oauth2"
API_URL = "https://api.cisco.com/test"


def _auth_ok(settings):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600}))
    return CiscoAuth(settings)


@respx.mock
def test_401_triggers_single_retry_then_succeeds(settings):
    auth = _auth_ok(settings)
    base = CiscoBaseClient(settings, auth)
    respx.get(API_URL).mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json={"ok": True})]
    )
    resp = base.request("GET", API_URL, tool="test")
    assert resp.status_code == 200


@respx.mock
def test_404_raises_without_retry(settings):
    auth = _auth_ok(settings)
    base = CiscoBaseClient(settings, auth)
    route = respx.get(API_URL).mock(return_value=httpx.Response(404, json={"error": "not found"}))
    try:
        base.request("GET", API_URL, tool="test")
        assert False
    except CiscoApiError as exc:
        assert exc.status_code == 404
    assert route.call_count == 1


@respx.mock
def test_403_raises(settings):
    auth = _auth_ok(settings)
    base = CiscoBaseClient(settings, auth)
    respx.get(API_URL).mock(return_value=httpx.Response(403))
    try:
        base.request("GET", API_URL, tool="test")
        assert False
    except CiscoApiError as exc:
        assert exc.status_code == 403


@respx.mock
def test_429_retries_then_succeeds(settings):
    auth = _auth_ok(settings)
    base = CiscoBaseClient(settings, auth)
    respx.get(API_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"ok": True})]
    )
    resp = base.request("GET", API_URL, tool="test")
    assert resp.status_code == 200


@respx.mock
def test_500_retries_then_gives_up(settings):
    auth = _auth_ok(settings)
    settings.http_max_retries = 1
    base = CiscoBaseClient(settings, auth)
    respx.get(API_URL).mock(return_value=httpx.Response(500))
    try:
        base.request("GET", API_URL, tool="test")
        assert False
    except CiscoApiError as exc:
        assert exc.status_code == 500
