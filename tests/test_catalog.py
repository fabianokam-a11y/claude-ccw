import json

import httpx
import respx

from app.auth import CiscoAuth
from app.clients.catalog import CiscoCatalogClient
from app.clients.commerce import CiscoApiError, CiscoBaseClient
from app.tools import pricing as pricing_tools

TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"
GQL = "https://capi.cisco.com/commerce/apis"


def _catalog(settings):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600}))
    return CiscoCatalogClient(CiscoBaseClient(settings, CiscoAuth(settings)), settings)


def _vc_response(lines, messages=None):
    return httpx.Response(200, json={"data": {"validateConfig": {"messages": messages or [], "lines": lines}}})


def _line(n, sku, qty, price):
    return {"configurationLineReference": {"lineId": n, "parentLineId": 0}, "item": {"sku": sku},
            "quantity": {"measurement": qty}, "configurationLineDetails": None,
            "financialDetails": {"unitListPrice": {"amount": price}}}


@respx.mock
def test_single_sku_list_price_and_total(settings):
    catalog = _catalog(settings)
    route = respx.post(GQL).mock(return_value=_vc_response([_line(1, "CW9176I-B", 50, 2684.56)]))
    out = pricing_tools.get_cisco_list_price(catalog, "cw9176i-b", 50)
    assert out["sku"] == "CW9176I-B"
    assert out["unit_list_price"] == 2684.56
    assert abs(out["total_list_price"] - 134228.0) < 0.01
    assert out["currency"] == "BRL" and out["price_list"] == "GLBRL"
    assert out["price_type"].startswith("Cisco GPL")
    sent = json.loads(route.calls[0].request.content)
    assert sent["variables"]["i"]["priceList"]["code"] == "GLBRL"
    assert sent["variables"]["i"]["lines"][0]["item"]["sku"] == "CW9176I-B"


@respx.mock
def test_unknown_sku_has_note_and_no_price(settings):
    catalog = _catalog(settings)
    respx.post(GQL).mock(return_value=_vc_response([]))
    out = pricing_tools.get_cisco_list_price(catalog, "NAO-EXISTE", 1)
    assert out["unit_list_price"] is None
    assert "GLUS" in out["note"]


@respx.mock
def test_batch_prices_is_one_http_call(settings):
    catalog = _catalog(settings)
    route = respx.post(GQL).mock(
        return_value=_vc_response([_line(1, "CW9164I-B", 48, 100.0), _line(2, "C9300X-48HX", 4, 5000.0)])
    )
    out = pricing_tools.get_cisco_prices(catalog, [{"sku": "CW9164I-B", "quantity": 48},
                                                   {"sku": "C9300X-48HX", "quantity": 4}], "GLUS")
    assert route.call_count == 1
    assert out["grand_total"] == 48 * 100.0 + 4 * 5000.0
    assert out["currency"] == "USD"


@respx.mock
def test_not_entitled_graphql_error_is_raised_readable(settings):
    catalog = _catalog(settings)
    respx.post(GQL).mock(return_value=httpx.Response(200, json={"errors": [{"message": "User is not entitled"}]}))
    try:
        catalog.get_prices([("X", 1)])
        assert False
    except CiscoApiError as exc:
        assert "not entitled" in str(exc)


@respx.mock
def test_invalid_quantity_rejected(settings):
    catalog = _catalog(settings)
    out = pricing_tools.get_cisco_prices(catalog, [{"sku": "X", "quantity": 0}])
    assert "error" in out
