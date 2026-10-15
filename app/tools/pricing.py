from __future__ import annotations

from typing import Optional

from pydantic import ValidationError

from app.clients.catalog import CiscoCatalogClient
from app.models.estimate import ItemInput


def get_cisco_list_price(
    catalog: CiscoCatalogClient, sku: str, quantity: float = 1, price_list: Optional[str] = None
) -> dict:
    item = ItemInput(sku=sku, quantity=quantity)
    table = catalog.get_prices([(item.sku, item.quantity)], price_list)
    r = table.items[0]
    out = r.model_dump()
    out["price_source"] = "Cisco Commerce (validateConfig)"
    if table.messages:
        out["messages"] = table.messages
    if table.additional_lines:
        out["additional_lines"] = table.additional_lines
    return out


def get_cisco_prices(catalog: CiscoCatalogClient, items: list[dict], price_list: Optional[str] = None) -> dict:
    try:
        parsed = [ItemInput(sku=i["sku"], quantity=i.get("quantity", 1)) for i in items]
    except (KeyError, ValidationError) as exc:
        return {"error": f"Itens inválidos: {exc}"}
    return catalog.get_prices([(p.sku, p.quantity) for p in parsed], price_list).model_dump()
