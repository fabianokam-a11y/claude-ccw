from __future__ import annotations

from app.clients.catalog import CiscoCatalogClient


def search_cisco_product(catalog: CiscoCatalogClient, query: str) -> dict:
    results = catalog.search_product(query)
    return {"query": query, "results": [r.model_dump() for r in results]}


def get_cisco_product(catalog: CiscoCatalogClient, sku: str) -> dict:
    product = catalog.get_product(sku)
    return product.model_dump()
