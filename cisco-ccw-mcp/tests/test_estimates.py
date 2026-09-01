import httpx
import respx

from app.auth import CiscoAuth
from app.clients.commerce import CiscoApiError, CiscoBaseClient
from app.clients.estimates import CiscoEstimateClient
from app.models.estimate import EstimateItemInput
from app.tools import estimates as estimate_tools

TOKEN_URL = "https://cloudsso.cisco.com/as/token.oauth2"


def _client(settings):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600}))
    auth = CiscoAuth(settings)
    base = CiscoBaseClient(settings, auth)
    return CiscoEstimateClient(base, settings)


@respx.mock
def test_create_estimate_dry_run_does_not_hit_network(settings):
    settings.ccw_dry_run = True
    client = _client(settings)
    create_route = respx.post("https://apix.cisco.com/commerce/EST/v2/async/createEstimate")

    result = client.create_estimate("Projeto XYZ", [EstimateItemInput(sku="CW9164I-B", quantity=48)])

    assert result.dry_run is True
    assert create_route.call_count == 0
    assert "CW9164I-B" in result.raw["would_send_xml"]


@respx.mock
def test_create_estimate_real_call_when_not_dry_run(settings):
    settings.ccw_dry_run = False
    client = _client(settings)
    respx.post("https://apix.cisco.com/commerce/EST/v2/async/createEstimate").mock(
        return_value=httpx.Response(
            200,
            text=(
                "<Estimate><EstimateId>123456</EstimateId><EstimateName>Projeto XYZ</EstimateName>"
                "<Status>Draft</Status><Total>128858.88</Total><Currency>USD</Currency>"
                "<Items><Item><SKU>CW9164I-B</SKU><Quantity>48</Quantity><UnitPrice>2684.56</UnitPrice></Item></Items>"
                "</Estimate>"
            ),
        )
    )
    result = client.create_estimate("Projeto XYZ", [EstimateItemInput(sku="CW9164I-B", quantity=48)])
    assert result.estimate_id == "123456"
    assert result.items[0].quantity == 48


@respx.mock
def test_tool_layer_blocks_write_without_confirm(settings):
    settings.ccw_dry_run = False
    client = _client(settings)
    create_route = respx.post("https://apix.cisco.com/commerce/EST/v2/async/createEstimate")

    result = estimate_tools.create_ccw_estimate(
        client, "Projeto XYZ", [{"sku": "CW9164I-B", "quantity": 48}], confirm=False
    )

    assert result["confirmation_required"] is True
    assert create_route.call_count == 0  # nada foi enviado sem confirmação


@respx.mock
def test_delete_estimate_requires_confirmation(settings):
    settings.ccw_dry_run = False
    client = _client(settings)
    delete_route = respx.post("https://apix.cisco.com/commerce/EST/v2/async/deleteEstimate")

    preview = estimate_tools.delete_ccw_estimate(client, "123456", confirm=False)
    assert preview["confirmation_required"] is True
    assert delete_route.call_count == 0


@respx.mock
def test_get_estimate_not_found_raises(settings):
    client = _client(settings)
    respx.post("https://apix.cisco.com/commerce/EST/v2/async/acquireEstimate").mock(
        return_value=httpx.Response(404, json={"error": "Estimate not found"})
    )
    try:
        client.get_estimate("999999")
        assert False
    except CiscoApiError as exc:
        assert exc.status_code == 404
