import json

import httpx
import respx

from app.auth import CiscoAuth
from app.clients.commerce import CiscoApiError, CiscoBaseClient
from app.clients.estimates import CiscoEstimateClient
from app.tools import estimates as tools

TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"
GQL = "https://capi.cisco.com/commerce/apis"


def _client(settings):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600}))
    return CiscoEstimateClient(CiscoBaseClient(settings, CiscoAuth(settings)), settings)


def _src_line(n, parent, sku, qty, path=None):
    return {"line": {"configurationLineReference": {"lineId": n * 10, "parentLineId": parent * 10 if parent else 0},
                     "item": {"sku": sku}, "quantity": {"measurement": qty}, "duration": None,
                     "configurationLineDetails": {"selectedBy": "USER", "path": path, "hashKey": None},
                     "financialDetails": {"discounts": []}}}


def _src_response(lines):
    return httpx.Response(200, json={"data": {"getEstimate": {
        "uuid": "u-1", "id": "QI1", "name": "BoM teste", "priceList": {"code": "GLBRL"}, "lines": lines}}})


ITEMS = [{"sku": "C9500-48Y4C-A", "quantity": 2}]


@respx.mock
def test_create_dry_run_never_hits_graphql(settings):
    settings.ccw_dry_run = True
    client = _client(settings)
    route = respx.post(GQL)
    out = tools.create_ccw_estimate(client, "TESTE_API_x", ITEMS, confirm=True)
    assert out["dry_run"] is True and route.call_count == 0
    assert out["would_send"]["operation"] == "createEstimate"
    assert out["would_send"]["variables"]["i"]["estimateReference"]["priceList"]["code"] == "GLBRL"


@respx.mock
def test_write_blocked_without_confirm(settings):
    settings.ccw_dry_run = False
    client = _client(settings)
    route = respx.post(GQL)
    for out in (
        tools.create_ccw_estimate(client, "x", ITEMS),
        tools.add_item_to_ccw_estimate(client, "QI1", "C9500-48Y4C-A", 1),
        tools.update_ccw_estimate_item(client, "QI1", "C9500-48Y4C-A", 3),
        tools.remove_ccw_estimate_item(client, "QI1", "C9500-48Y4C-A"),
        tools.share_ccw_estimate(client, "QI1", ["a@napit.com.br"]),
    ):
        assert out["confirmation_required"] is True
    assert route.call_count == 0


@respx.mock
def test_create_real_and_auto_share(settings):
    settings.ccw_dry_run = False
    settings.ccw_share_emails = "fabiano.alves@napit.com.br"
    client = _client(settings)
    route = respx.post(GQL).mock(side_effect=[
        httpx.Response(200, json={"data": {"createEstimate": {"id": "QI9", "name": "n", "estimateStatus": "VALID",
                                                              "messages": []}}}),
        httpx.Response(200, json={"data": {"shareEstimate": {"id": "QI9", "messages": []}}}),
    ])
    out = tools.create_ccw_estimate(client, "n", ITEMS, "GLUS", confirm=True)
    assert out["id"] == "QI9" and out["dry_run"] is False
    assert out["shared"]["id"] == "QI9"
    created = json.loads(route.calls[0].request.content)["variables"]["i"]
    assert created["estimateReference"]["priceList"]["code"] == "GLUS"
    shared = json.loads(route.calls[1].request.content)["variables"]["i"]
    assert shared["shareDetails"][0]["permission"] == "READ_WRITE"


@respx.mock
def test_update_quantity_resends_all_lines_preserving_path(settings):
    settings.ccw_dry_run = False
    client = _client(settings)
    route = respx.post(GQL).mock(side_effect=[
        _src_response([_src_line(1, 0, "C9300-24P", 1), _src_line(2, 1, "C9300-NM-4G", 1, path="P:1")]),
        httpx.Response(200, json={"data": {"updateEstimate": {"id": "QI1", "name": "BoM teste",
                                                              "estimateStatus": "UNVERIFIED", "messages": []}}}),
    ])
    out = tools.update_ccw_estimate_item(client, "QI1", "C9300-24P", 5, confirm=True)
    assert "NÃO reprecifica" in out["warning"]
    sent = json.loads(route.calls[1].request.content)["variables"]["i"]
    assert sent["uuid"] == "u-1" and len(sent["lines"]) == 2
    assert sent["lines"][0]["line"]["quantity"]["measurement"] == 5
    assert sent["lines"][1]["line"]["configurationDetailsInput"]["path"] == "P:1"
    assert sent["lines"][1]["line"]["configurationLineReferenceInput"]["parentLineId"] == 1


@respx.mock
def test_remove_item_reparents_children(settings):
    settings.ccw_dry_run = True
    client = _client(settings)
    respx.post(GQL).mock(return_value=_src_response(
        [_src_line(1, 0, "ROOT", 1), _src_line(2, 1, "MID", 1), _src_line(3, 2, "LEAF", 1)]))
    out = tools.remove_ccw_estimate_item(client, "QI1", "mid", confirm=True)
    lines = out["would_send"]["variables"]["i"]["lines"]
    assert [l["line"]["item"]["sku"] for l in lines] == ["ROOT", "LEAF"]
    assert lines[1]["line"]["configurationLineReferenceInput"]["parentLineId"] == 1


@respx.mock
def test_remove_unknown_sku_raises_value_error(settings):
    client = _client(settings)
    respx.post(GQL).mock(return_value=_src_response([_src_line(1, 0, "ROOT", 1)]))
    try:
        client.remove_item("QI1", "NOPE")
        assert False
    except ValueError as exc:
        assert "NOPE" in str(exc)


@respx.mock
def test_get_estimate_normalizes_lines_and_total(settings):
    client = _client(settings)
    line = {"line": {"configurationLineReference": {"lineId": 7, "parentLineId": 0},
                     "item": {"sku": "A", "description": "d"}, "quantity": {"measurement": 2}, "duration": None,
                     "financialDetails": {"unitListPrice": {"amount": 10, "currency": "BRL"}, "discounts": [],
                                          "unitNetPrice": {"amount": 10}, "extendedNetPrice": {"amount": 20}}}}
    respx.post(GQL).mock(return_value=httpx.Response(200, json={"data": {"getEstimate": {
        "id": "QI1", "name": "n", "estimateStatus": "VALID", "uuid": "u",
        "priceList": {"code": "GLBRL", "currencies": ["BRL"]}, "messages": [], "lines": [line]}}}))
    out = client.get_estimate("QI1")
    assert out["total_net_price"] == 20 and out["currency"] == "BRL"
    assert out["lines"][0]["unit_list_price"] == 10


@respx.mock
def test_estimate_not_shared_error_is_readable(settings):
    client = _client(settings)
    respx.post(GQL).mock(return_value=httpx.Response(200, json={"errors": [{"message": "not entitled"}]}))
    try:
        client.get_estimate("QI1")
        assert False
    except CiscoApiError as exc:
        assert "not entitled" in str(exc)


@respx.mock
def test_search_estimates(settings):
    client = _client(settings)
    respx.post(GQL).mock(return_value=httpx.Response(200, json={"data": {"searchEstimate": {"objects": [
        {"id": "QI1", "name": "BoM_BR_ID15695 X", "estimateStatus": "VALID", "priceList": {"code": "GLBRL"}}]}}}))
    assert tools.search_ccw_estimates(client, "15695")["estimates"][0]["estimate_id"] == "QI1"
