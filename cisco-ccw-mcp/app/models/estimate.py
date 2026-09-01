from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class EstimateItemInput(BaseModel):
    sku: str
    quantity: int


class EstimateItem(BaseModel):
    sku: str
    description: Optional[str] = None
    quantity: int
    unit_price: Optional[float] = None
    total_price: Optional[float] = None


class Estimate(BaseModel):
    estimate_id: Optional[str] = None
    name: str
    status: Optional[str] = None
    items: list[EstimateItem] = []
    subtotal: Optional[float] = None
    total: Optional[float] = None
    currency: str = "USD"
    created_date: Optional[str] = None
    ccw_url: Optional[str] = None
    dry_run: bool = False
    raw: Optional[dict] = None
