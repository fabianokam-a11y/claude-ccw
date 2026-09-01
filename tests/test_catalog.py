import httpx
import respx

from app.auth import CiscoAuth
from app.clients.catalog import CiscoCatalogClient
from app.clients.commerce import CiscoApiError, CiscoBaseClient

TOKEN_URL = "https://cloudsso.cisco.com/as/token.oauth2"


def _catalog(settings):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600}))
    auth = CiscoAuth(settings)
    base = CiscoBaseClient(settings, auth)
    return CiscoCatalogClient(base, settings.cisco_api_base_url, settings.default_currency)


@respx.mock
def test_get_product_valid_sku(settings):
    catalog = _catalog(settings)
    respx.get("https://api.cisco.com/commerce/PXP/v2/catalog/items/CW9164I-B").mock(
        return_value=httpx.Response(
            200,
            json={"sku": "CW9164I-B", "description": "Catalyst 9164I AP", "listPrice": 2684.56, "currency": "USD"},
        )
    )
    product = catalog.get_product("CW9164I-B")
    assert product.sku == "CW9164I-B"
    assert product.list_price == 2684.56


@respx.mock
def test_get_product_nonexistent_sku_raises(settings):
    catalog = _catalog(settings)
    respx.get("https://api.cisco.com/commerce/PXP/v2/catalog/items/DOES-NOT-EXIST").mock(
        return_value=httpx.Response(404, json={"error": "SKU not found"})
    )
    try:
        catalog.get_product("DOES-NOT-EXIST")
        assert False
    except CiscoApiError as exc:
        assert exc.status_code == 404


@respx.mock
def test_get_prices_multiple_skus_computes_grand_total(settings):
    catalog = _catalog(settings)
    respx.post("https://api.cisco.com/commerce/PXP/v2/pricelist/items").mock(
        return_value=httpx.Response(
            200,
            json={
                "currency": "USD",
                "items": [
                    {"description": "AP", "unitListPrice": 2684.56},
                    {"description": "Switch", "unitListPrice": 5000.00},
                ],
            },
        )
    )
    table = catalog.get_prices([("CW9164I-B", 48), ("C9300X-48HX", 4)])
    expected = 2684.56 * 48 + 5000.00 * 4
    assert abs(table.grand_total - expected) < 0.01
    assert len(table.items) == 2
