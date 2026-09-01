from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ProductSummary(BaseModel):
    sku: str
    description: Optional[str] = None
    family: Optional[str] = None
    status: Optional[str] = None
    list_price: Optional[float] = None
    currency: Optional[str] = None


class ProductDetail(ProductSummary):
    raw: Optional[dict] = None  # payload bruto da Cisco, para inspeção quando necessário
