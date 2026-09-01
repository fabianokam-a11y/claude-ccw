from __future__ import annotations

from app.clients.catalog import CiscoCatalogClient


def get_cisco_list_price(catalog: CiscoCatalogClient, sku: str, quantity: int = 1) -> dict:
    table = catalog.get_prices([(sku, quantity)])
    item = table.items[0]
    return {
        "sku": item.sku,
        "description": item.description,
        "unit_list_price": item.unit_list_price,
        "quantity": item.quantity,
        "total_list_price": item.total_list_price,
        "currency": item.currency,
        "price_source": "Cisco",
    }


def get_cisco_prices(catalog: CiscoCatalogClient, items: list[dict]) -> dict:
    pairs = [(i["sku"], i.get("quantity", 1)) for i in items]
    table = catalog.get_prices(pairs)
    return table.model_dump()
