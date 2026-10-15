"""
Tools de Estimate. Toda escrita tem guardrail em duas camadas:
  1) prompt: o Claude resume e pede confirmação ao usuário;
  2) código: sem `confirm=True` a tool NÃO toca no CCW e devolve só um preview.
Além disso, CCW_DRY_RUN=true bloqueia qualquer envio real.
"""
from __future__ import annotations

from typing import Optional

from pydantic import ValidationError

from app.clients.estimates import CiscoEstimateClient
from app.models.estimate import ItemInput


def _needs_confirmation(preview: dict) -> dict:
    return {"confirmation_required": True, "preview": preview}


def _parse_items(items: list[dict]) -> list[ItemInput]:
    return [
        ItemInput(sku=i["sku"], quantity=i["quantity"], parent=i.get("parent", 0),
                  duration_months=i.get("duration_months"))
        for i in items
    ]


def search_ccw_estimates(client: CiscoEstimateClient, name: str) -> dict:
    found = client.search_estimates(name)
    return {"count": len(found), "estimates": found}


def get_ccw_estimate(client: CiscoEstimateClient, estimate_id: str) -> dict:
    return client.get_estimate(estimate_id)


def validate_ccw_estimate(client: CiscoEstimateClient, estimate_id: str) -> dict:
    return client.validate_estimate(estimate_id)


def create_ccw_estimate(
    client: CiscoEstimateClient, name: str, items: list[dict],
    price_list: Optional[str] = None, confirm: bool = False,
) -> dict:
    try:
        parsed = _parse_items(items)
    except (KeyError, ValidationError) as exc:
        return {"error": f"Itens inválidos: {exc}"}
    if not confirm:
        return _needs_confirmation({
            "action": "create_ccw_estimate", "name": name,
            "price_list": (price_list or client._settings.ccw_default_price_list).upper(),
            "items": [p.model_dump() for p in parsed],
            "note": "A price list não muda depois de criada. Subscrições saem com 36 meses.",
        })
    result = client.create_estimate(name, price_list, [p.to_line_item() for p in parsed])
    emails = client._settings.share_emails()
    if emails and result.get("id") and not result.get("dry_run"):
        result["shared"] = client.share_estimate(result["id"], emails)
    return result


def add_item_to_ccw_estimate(
    client: CiscoEstimateClient, estimate_id: str, sku: str, quantity: float,
    parent: int = 0, duration_months: Optional[int] = None, confirm: bool = False,
) -> dict:
    try:
        item = ItemInput(sku=sku, quantity=quantity, parent=parent, duration_months=duration_months)
    except ValidationError as exc:
        return {"error": f"Item inválido: {exc}"}
    if not confirm:
        return _needs_confirmation({"action": "add_item_to_ccw_estimate", "estimate_id": estimate_id,
                                    "item": item.model_dump(),
                                    "warning": "O update reenvia todas as linhas e não reprecifica."})
    return client.add_item(estimate_id, item.to_line_item())


def update_ccw_estimate_item(
    client: CiscoEstimateClient, estimate_id: str, sku: str, quantity: float, confirm: bool = False
) -> dict:
    try:
        item = ItemInput(sku=sku, quantity=quantity)
    except ValidationError as exc:
        return {"error": f"Item inválido: {exc}"}
    if not confirm:
        return _needs_confirmation({"action": "update_ccw_estimate_item", "estimate_id": estimate_id,
                                    "sku": item.sku, "quantity": item.quantity,
                                    "warning": "O update reenvia todas as linhas e não reprecifica."})
    return client.set_quantity(estimate_id, item.sku, item.quantity)


def remove_ccw_estimate_item(
    client: CiscoEstimateClient, estimate_id: str, sku: str, confirm: bool = False
) -> dict:
    sku = sku.strip().upper()
    if not confirm:
        return _needs_confirmation({"action": "remove_ccw_estimate_item", "estimate_id": estimate_id, "sku": sku,
                                    "warning": "Filhos da linha removida sobem para o avô. Não reprecifica."})
    return client.remove_item(estimate_id, sku)


def share_ccw_estimate(
    client: CiscoEstimateClient, estimate_id: str, emails: Optional[list[str]] = None, confirm: bool = False
) -> dict:
    targets = emails or client._settings.share_emails()
    if not targets:
        return {"error": "Nenhum e-mail informado e CCW_SHARE_EMAILS não está configurado."}
    if not confirm:
        return _needs_confirmation({"action": "share_ccw_estimate", "estimate_id": estimate_id,
                                    "emails": targets, "permission": "READ_WRITE"})
    return client.share_estimate(estimate_id, targets)
