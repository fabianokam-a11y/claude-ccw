from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


PriceSource = Literal["Cisco GPL", "Estimated", "Net", "Discount", "Partner"]


class SkuPriceRequest(BaseModel):
    sku: str
    quantity: int = 1


class SkuPrice(BaseModel):
    sku: str
    description: Optional[str] = None
    quantity: int
    unit_list_price: Optional[float] = None
    total_list_price: Optional[float] = None
    currency: str
    price_type: PriceSource = "Cisco GPL"
    net_unit_price: Optional[float] = None
    net_total_price: Optional[float] = None
    discount_percent: Optional[float] = None


class PriceTable(BaseModel):
    items: list[SkuPrice]
    grand_total: float
    currency: str
