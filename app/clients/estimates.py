"""
CiscoEstimateClient: estimates do CCW pela API GraphQL do Cisco Commerce.

Permissões do client da API (levantadas pelo time):
  liberado: getEstimate, validateEstimate, validateConfig, createEstimate,
            updateEstimate, shareEstimate, searchEstimate (parcial)
  negado:   copyEstimate, deleteEstimate, buildConfig, getItems

Pegadinhas que moldam este client:
  - Estimate só é legível depois de compartilhado com o usuário da API.
  - Price list é fixada na criação (GLBRL / GLICON / GLUS).
  - updateEstimate substitui TODAS as linhas e NÃO reprecifica.
  - Exclusão e cópia só pelo CCW.

MODO DRY RUN: com CCW_DRY_RUN=true as mutations (create/update/share) NÃO são
enviadas; o client devolve o payload que seria enviado.
"""
from __future__ import annotations

from typing import Optional

from app.clients.commerce import CiscoBaseClient
from app.clients.lines import CURRENCY_BY_PRICE_LIST, ZERO_UUID, build_lines, drop_items, now_local
from app.config import Settings

LINE_FIELDS = """lines { line { configurationLineReference{lineId parentLineId} item{sku description}
  quantity{measurement} duration{measurement}
  financialDetails{ unitListPrice{amount currency} discounts{rate{measurement}} unitNetPrice{amount} extendedNetPrice{amount} } } }"""

GET_Q = ("query($i:EstimateInput){ getEstimate(input:$i){ messages{code description} uuid id name estimateStatus "
         "priceList{code currencies} " + LINE_FIELDS + " } }")

VALIDATE_Q = ("query($i:EstimateInput){ validateEstimate(input:$i){ estimateStatus "
              "messages{code description severity} } }")

SRC_Q = """query($i:EstimateInput){ getEstimate(input:$i){ uuid id name priceList{code} lines { line {
 configurationLineReference{lineId parentLineId} item{sku} quantity{measurement} duration{measurement}
 configurationLineDetails{ selectedBy path hashKey } financialDetails{ discounts{rate{measurement}} } } } } }"""

SEARCH_Q = ("query($i:EstimateSearchInput){ searchEstimate(input:$i){ objects{ id name estimateStatus priceList{code} } } }")

CREATE_M = ("mutation($i:EstimateInput){ createEstimate(input:$i){ messages{code description severity} "
            "uuid id name estimateStatus } }")
UPDATE_M = ("mutation($i:EstimateInput){ updateEstimate(input:$i){ messages{code description severity} "
            "id name estimateStatus } }")
SHARE_M = "mutation($i:EstimateInput){ shareEstimate(input:$i){ messages{code description} id } }"


def _ref(eid: str) -> dict:
    return {"uuid": ZERO_UUID, "createdDateTime": now_local(), "estimateReference": {"id": eid}}


class CiscoEstimateClient:
    def __init__(self, base: CiscoBaseClient, settings: Settings):
        self._base = base
        self._settings = settings
        self._url = settings.ccw_graphql_url

    def _gql(self, query: str, variables: dict, tool: str) -> dict:
        return self._base.graphql(self._url, query, variables, tool=tool)

    def _write(self, tool: str, mutation: str, variables: dict, result_key: str) -> dict:
        if self._settings.ccw_dry_run:
            return {
                "dry_run": True,
                "status": "DRY_RUN — nada foi enviado ao CCW",
                "would_send": {"endpoint": self._url, "operation": result_key, "variables": variables},
            }
        data = self._gql(mutation, variables, tool)
        return {"dry_run": False, **(data.get(result_key) or {})}

    # ---------- leitura ----------

    def get_estimate(self, estimate_id: str) -> dict:
        e = (self._gql(GET_Q, {"i": _ref(estimate_id)}, "get_ccw_estimate")).get("getEstimate") or {}
        raw_lines = [x["line"] for x in (e.get("lines") or [])]
        pos = {l["configurationLineReference"]["lineId"]: n for n, l in enumerate(raw_lines, 1)}
        lines, total = [], 0.0
        for n, l in enumerate(raw_lines, 1):
            f = l["financialDetails"]
            ext = (f["extendedNetPrice"] or {}).get("amount") or 0
            total += ext
            lines.append({
                "n": n,
                "parent": pos.get(l["configurationLineReference"]["parentLineId"], 0),
                "sku": l["item"]["sku"],
                "description": l["item"].get("description"),
                "quantity": l["quantity"]["measurement"],
                "duration_months": (l["duration"] or {}).get("measurement") if l.get("duration") else None,
                "unit_list_price": (f["unitListPrice"] or {}).get("amount"),
                "discount_percent": f["discounts"][0]["rate"]["measurement"] if f.get("discounts") else 0,
                "unit_net_price": (f.get("unitNetPrice") or {}).get("amount"),
                "extended_net_price": ext,
            })
        pl = (e.get("priceList") or {}).get("code")
        currency = ((e.get("priceList") or {}).get("currencies") or [CURRENCY_BY_PRICE_LIST.get(pl, "?")])[0]
        return {
            "estimate_id": e.get("id"), "name": e.get("name"), "status_saved": e.get("estimateStatus"),
            "price_list": pl, "currency": currency, "lines": lines,
            "total_net_price": total, "messages": e.get("messages") or [],
            "note": "status_saved é o status gravado; use validate para o status atual.",
        }

    def validate_estimate(self, estimate_id: str) -> dict:
        v = (self._gql(VALIDATE_Q, {"i": _ref(estimate_id)}, "validate_ccw_estimate")).get("validateEstimate") or {}
        return {
            "estimate_id": estimate_id,
            "status": v.get("estimateStatus"),
            "messages": [{"severity": m.get("severity"), "code": m.get("code"),
                          "description": (m.get("description") or "")[:300]} for m in v.get("messages") or []],
        }

    def search_estimates(self, name: str, page_size: int = 50) -> list[dict]:
        inp = {
            "estimateSearchCriteria": [{"estimateSearchKey": "ESTIMATE_NAME", "estimateSearchValue": name}],
            "sortBy": "LAST_MODIFIED",
            "pagination": {"page": 1, "pageSize": page_size},
        }
        d = self._gql(SEARCH_Q, {"i": inp}, "search_ccw_estimates")
        return [
            {"estimate_id": o["id"], "name": o["name"], "status_saved": o["estimateStatus"],
             "price_list": (o.get("priceList") or {}).get("code")}
            for o in ((d.get("searchEstimate") or {}).get("objects") or [])
        ]

    def _source(self, estimate_id: str) -> tuple[dict, list[dict]]:
        """Lê meta + linhas preservando path/hashKey/selectedBy (necessário p/ reenviar tudo)."""
        e = (self._gql(SRC_Q, {"i": _ref(estimate_id)}, "read_estimate_lines")).get("getEstimate") or {}
        orig = [x["line"] for x in (e.get("lines") or [])]
        idx = {l["configurationLineReference"]["lineId"]: n for n, l in enumerate(orig, 1)}
        items = []
        for l in orig:
            c = l.get("configurationLineDetails") or {}
            f = l["financialDetails"]
            items.append({
                "sku": l["item"]["sku"], "qty": l["quantity"]["measurement"],
                "parent": idx.get(l["configurationLineReference"]["parentLineId"], 0),
                "dur": (l.get("duration") or {}).get("measurement"),
                "disc": f["discounts"][0]["rate"]["measurement"] if f.get("discounts") else 0,
                "sel": c.get("selectedBy"), "path": c.get("path"), "hash": c.get("hashKey"),
            })
        meta = {"uuid": e.get("uuid"), "id": e.get("id"), "name": e.get("name"),
                "price_list": (e.get("priceList") or {}).get("code")}
        return meta, items

    # ---------- escrita (respeitam CCW_DRY_RUN) ----------

    def create_estimate(self, name: str, price_list: Optional[str], items: list[dict]) -> dict:
        pl = (price_list or self._settings.ccw_default_price_list).upper()
        inp = {"uuid": ZERO_UUID, "createdDateTime": now_local(),
               "estimateReference": {"name": name, "priceList": {"code": pl}},
               "lines": build_lines(items)}
        return self._write("create_ccw_estimate", CREATE_M, {"i": inp}, "createEstimate")

    def _replace_lines(self, tool: str, meta: dict, items: list[dict]) -> dict:
        inp = {"uuid": meta["uuid"], "createdDateTime": now_local(),
               "estimateReference": {"id": meta["id"], "name": meta["name"],
                                     "priceList": {"code": meta["price_list"]}},
               "lines": build_lines(items)}
        res = self._write(tool, UPDATE_M, {"i": inp}, "updateEstimate")
        res["warning"] = ("updateEstimate substitui todas as linhas e NÃO reprecifica: o estimate pode ficar "
                          "UNVERIFIED e serviços/subscrições com preço 0. Se o preço importa, recrie o estimate.")
        return res

    def add_item(self, estimate_id: str, item: dict) -> dict:
        meta, items = self._source(estimate_id)
        if item.get("parent", 0) > len(items):
            raise ValueError(f"Linha pai {item['parent']} não existe (estimate tem {len(items)} linhas).")
        return self._replace_lines("add_item_to_ccw_estimate", meta, items + [item])

    def set_quantity(self, estimate_id: str, sku: str, quantity: float) -> dict:
        meta, items = self._source(estimate_id)
        matches = [i for i, it in enumerate(items) if it["sku"] == sku]
        if not matches:
            raise ValueError(f"SKU {sku} não encontrado no estimate {estimate_id}.")
        if len(matches) > 1:
            raise ValueError(f"SKU {sku} aparece em {len(matches)} linhas; ajuste pelo CCW para evitar ambiguidade.")
        items[matches[0]]["qty"] = quantity
        return self._replace_lines("update_ccw_estimate_item", meta, items)

    def remove_item(self, estimate_id: str, sku: str) -> dict:
        meta, items = self._source(estimate_id)
        if not any(it["sku"] == sku for it in items):
            raise ValueError(f"SKU {sku} não encontrado no estimate {estimate_id}.")
        return self._replace_lines("remove_ccw_estimate_item", meta, drop_items(items, {sku}))

    def share_estimate(self, estimate_id: str, emails: list[str]) -> dict:
        inp = _ref(estimate_id)
        inp["shareDetails"] = [{"sharedWith": {"primaryEmail": e}, "permission": "READ_WRITE"} for e in emails]
        return self._write("share_ccw_estimate", SHARE_M, {"i": inp}, "shareEstimate")
