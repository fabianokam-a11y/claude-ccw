"""
CiscoCatalogClient: busca de produtos e preços (GPL).

ATENÇÃO — AÇÃO NECESSÁRIA DE SUA PARTE:
Os paths abaixo (`/commerce/catalog/...`, `/commerce/pricelist/...`) são os
nomes convencionais usados pela Xpress Connect "Prepare Configuration API" e
"Price List API", mas a Cisco não publica um contrato REST único e estável
publicamente — o path exato depende de qual versão foi habilitada para o SEU
app no API Console (isso aparece na aba de documentação do app, ex:
"Prepare Configuration API v1/v2"). Antes do primeiro teste real:

  1. Abra seu app em apiconsole.cisco.com
  2. Copie o path exato mostrado na doc do "Prepare Configuration API" e do
     "Price List API"
  3. Ajuste as constantes SEARCH_PATH / PRODUCT_PATH / PRICE_PATH abaixo

Isso é intencional: preferi deixar o client funcional e testável (inclusive
com testes que mockam a resposta) a inventar um endpoint e fingir que está
validado contra a documentação oficial.
"""
from __future__ import annotations

from typing import Optional

from app.clients.commerce import CiscoApiError, CiscoBaseClient
from app.models.pricing import PriceTable, SkuPrice
from app.models.product import ProductDetail, ProductSummary

SEARCH_PATH = "/commerce/PXP/v2/catalog/search"
PRODUCT_PATH = "/commerce/PXP/v2/catalog/items/{sku}"
PRICE_PATH = "/commerce/PXP/v2/pricelist/items"


class CiscoCatalogClient:
    def __init__(self, base: CiscoBaseClient, api_base_url: str, default_currency: str):
        self._base = base
        self._api_base_url = api_base_url.rstrip("/")
        self._default_currency = default_currency

    def search_product(self, query: str) -> list[ProductSummary]:
        resp = self._base.request(
            "GET",
            f"{self._api_base_url}{SEARCH_PATH}",
            tool="search_cisco_product",
            params={"q": query},
        )
        body = resp.json()
        items = body.get("items", body.get("results", []))
        return [self._to_summary(item) for item in items]

    def get_product(self, sku: str) -> ProductDetail:
        resp = self._base.request(
            "GET",
            f"{self._api_base_url}{PRODUCT_PATH.format(sku=sku)}",
            tool="get_cisco_product",
        )
        body = resp.json()
        summary = self._to_summary(body)
        return ProductDetail(**summary.model_dump(), raw=body)

    def get_prices(self, items: list[tuple[str, int]]) -> PriceTable:
        """Consulta em lote — evita 1 chamada HTTP por SKU."""
        resp = self._base.request(
            "POST",
            f"{self._api_base_url}{PRICE_PATH}",
            tool="get_cisco_prices",
            json_body={
                "items": [{"sku": sku, "quantity": qty} for sku, qty in items]
            },
        )
        body = resp.json()
        prices: list[SkuPrice] = []
        currency = body.get("currency", self._default_currency)
        for raw_item, (sku, qty) in zip(body.get("items", []), items):
            unit = raw_item.get("unitListPrice") or raw_item.get("unit_list_price")
            total = (unit * qty) if unit is not None else None
            prices.append(
                SkuPrice(
                    sku=sku,
                    description=raw_item.get("description"),
                    quantity=qty,
                    unit_list_price=unit,
                    total_list_price=total,
                    currency=raw_item.get("currency", currency),
                    price_type="Cisco GPL",
                )
            )
        grand_total = sum(p.total_list_price or 0 for p in prices)
        return PriceTable(items=prices, grand_total=grand_total, currency=currency)

    @staticmethod
    def _to_summary(item: dict) -> ProductSummary:
        return ProductSummary(
            sku=item.get("sku") or item.get("partNumber") or item.get("id", ""),
            description=item.get("description") or item.get("shortDescription"),
            family=item.get("family") or item.get("productFamily"),
            status=item.get("status") or item.get("lifecycleStatus"),
            list_price=item.get("listPrice") or item.get("unitListPrice"),
            currency=item.get("currency"),
        )
