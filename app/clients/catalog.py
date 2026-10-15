"""
CiscoCatalogClient: preço de lista (GPL) via `validateConfig`.

`validateConfig` é um sandbox somente-leitura: valida uma configuração e
devolve `unitListPrice` por linha SEM criar estimate no CCW. É o caminho
usado pelo time (a API não libera getItems/busca de catálogo).
"""
from __future__ import annotations

from typing import Optional

from app.clients.commerce import CiscoBaseClient
from app.clients.lines import CURRENCY_BY_PRICE_LIST, ZERO_UUID, build_lines, now_local
from app.config import Settings
from app.models.pricing import PriceTable, SkuPrice

VALIDATE_CONFIG_Q = """query($i:ConfigurationInput){ validateConfig(input:$i){ messages{code description severity}
 lines{ configurationLineReference{lineId parentLineId} item{sku} quantity{measurement}
 configurationLineDetails{selectedBy path hashKey} financialDetails{unitListPrice{amount}} } } }"""


class CiscoCatalogClient:
    def __init__(self, base: CiscoBaseClient, settings: Settings):
        self._base = base
        self._settings = settings

    def get_prices(self, items: list[tuple[str, float]], price_list: Optional[str] = None) -> PriceTable:
        pl = (price_list or self._settings.ccw_default_price_list).upper()
        currency = CURRENCY_BY_PRICE_LIST.get(pl, "?")
        line_items = [{"sku": sku, "qty": qty} for sku, qty in items]
        inp = {
            "uuid": ZERO_UUID,
            "createdDateTime": now_local(),
            "priceList": {"code": pl},
            "lines": [l["line"] for l in build_lines(line_items)],
        }
        data = self._base.graphql(self._settings.ccw_graphql_url, VALIDATE_CONFIG_Q, {"i": inp}, tool="get_cisco_prices")
        cfg = data.get("validateConfig") or {}

        messages = [
            f"{m['code']}: {m['description'][:200]}"
            for m in (cfg.get("messages") or [])
            if m.get("severity") == "ERROR"
        ]

        returned = cfg.get("lines") or []
        by_sku: dict[str, dict] = {}
        for ln in returned:
            by_sku.setdefault(ln["item"]["sku"], ln)

        results: list[SkuPrice] = []
        for sku, qty in items:
            ln = by_sku.get(sku)
            unit = None
            if ln:
                unit = ((ln.get("financialDetails") or {}).get("unitListPrice") or {}).get("amount")
            note = None
            if ln is None:
                note = "SKU não retornado pela Cisco (inexistente ou fora desta price list)."
            elif not unit:
                note = "Sem preço de lista nesta price list."
            if note and pl == "GLBRL":
                note += " Tente GLUS ou GLICON (Meraki/LATAM não existem no GLBRL)."
            results.append(
                SkuPrice(
                    sku=sku,
                    quantity=qty,
                    unit_list_price=unit,
                    total_list_price=(unit * qty) if unit else None,
                    currency=currency,
                    price_list=pl,
                    note=note,
                )
            )

        requested = {sku for sku, _ in items}
        extra = [
            {"sku": ln["item"]["sku"], "quantity": ln["quantity"]["measurement"],
             "unit_list_price": ((ln.get("financialDetails") or {}).get("unitListPrice") or {}).get("amount")}
            for ln in returned
            if ln["item"]["sku"] not in requested
        ]
        return PriceTable(
            price_list=pl,
            currency=currency,
            items=results,
            grand_total=sum(r.total_list_price or 0 for r in results),
            messages=messages,
            additional_lines=extra,
        )
