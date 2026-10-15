from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ItemInput(BaseModel):
    """Item de entrada nas tools. `parent` é o índice 1-based da linha pai (0 = raiz)."""

    sku: str
    quantity: float = Field(gt=0)
    parent: int = Field(default=0, ge=0)
    duration_months: Optional[int] = Field(default=None, gt=0)

    @field_validator("sku")
    @classmethod
    def _clean_sku(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("SKU vazio")
        return v

    def to_line_item(self) -> dict:
        item = {"sku": self.sku, "qty": self.quantity, "parent": self.parent}
        if self.duration_months:
            item["dur"] = self.duration_months
        return item
