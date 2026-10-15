from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SkuPrice(BaseModel):
    sku: str
    quantity: float
    unit_list_price: Optional[float] = None
    total_list_price: Optional[float] = None
    currency: str
    price_type: str = "Cisco GPL / List Price"
    price_list: str
    note: Optional[str] = None


class PriceTable(BaseModel):
    price_list: str
    currency: str
    items: list[SkuPrice]
    grand_total: float
    messages: list[str] = []
    additional_lines: list[dict] = []
