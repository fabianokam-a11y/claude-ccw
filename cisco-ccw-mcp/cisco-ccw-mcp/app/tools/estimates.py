"""
Tools de Estimate.

Guardrail em duas camadas para toda operação de escrita:
  1) Camada de prompt: o Claude deve resumir a operação e pedir confirmação
     ao usuário antes de chamar a tool com confirm=True.
  2) Camada de código (esta aqui): toda tool de escrita exige o parâmetro
     `confirm=True`. Se vier False/ausente, a tool NÃO toca no CCW — apenas
     devolve um preview do que seria feito, para o Claude apresentar ao
     usuário antes de repetir a chamada com confirm=True.

Isso garante que uma alucinação do modelo (chamar a tool sem ter
efetivamente perguntado ao usuário) não seja suficiente para alterar o CCW.
"""
from __future__ import annotations

from app.clients.estimates import CiscoEstimateClient
from app.models.estimate import EstimateItemInput


def _needs_confirmation(preview: dict) -> dict:
    return {"confirmation_required": True, "preview": preview}


def create_ccw_estimate(client: CiscoEstimateClient, name: str, items: list[dict], confirm: bool = False) -> dict:
    parsed_items = [EstimateItemInput(sku=i["sku"], quantity=i["quantity"]) for i in items]
    if not confirm:
        return _needs_confirmation({"action": "create_ccw_estimate", "name": name, "items": items})
    return client.create_estimate(name, parsed_items).model_dump()


def get_ccw_estimate(client: CiscoEstimateClient, estimate_id: str) -> dict:
    return client.get_estimate(estimate_id).model_dump()


def list_ccw_estimates(
    client: CiscoEstimateClient,
    limit: int | None = None,
    status: str | None = None,
    created_after: str | None = None,
    search: str | None = None,
) -> dict:
    estimates = client.list_estimates(limit=limit, status=status, created_after=created_after, search=search)
    return {"count": len(estimates), "estimates": [e.model_dump() for e in estimates]}


def add_item_to_ccw_estimate(
    client: CiscoEstimateClient, estimate_id: str, sku: str, quantity: int, confirm: bool = False
) -> dict:
    if not confirm:
        return _needs_confirmation(
            {"action": "add_item_to_ccw_estimate", "estimate_id": estimate_id, "sku": sku, "quantity": quantity}
        )
    return client.add_or_update_item(estimate_id, sku, quantity).model_dump()


def update_ccw_estimate_item(
    client: CiscoEstimateClient, estimate_id: str, sku: str, quantity: int, confirm: bool = False
) -> dict:
    if not confirm:
        return _needs_confirmation(
            {"action": "update_ccw_estimate_item", "estimate_id": estimate_id, "sku": sku, "quantity": quantity}
        )
    return client.add_or_update_item(estimate_id, sku, quantity).model_dump()


def remove_ccw_estimate_item(client: CiscoEstimateClient, estimate_id: str, sku: str, confirm: bool = False) -> dict:
    if not confirm:
        return _needs_confirmation({"action": "remove_ccw_estimate_item", "estimate_id": estimate_id, "sku": sku})
    return client.remove_item(estimate_id, sku).model_dump()


def delete_ccw_estimate(client: CiscoEstimateClient, estimate_id: str, confirm: bool = False) -> dict:
    if not confirm:
        return _needs_confirmation({"action": "delete_ccw_estimate", "estimate_id": estimate_id})
    return client.delete_estimate(estimate_id)


def duplicate_ccw_estimate(
    client: CiscoEstimateClient, estimate_id: str, new_name: str, confirm: bool = False
) -> dict:
    if not confirm:
        return _needs_confirmation(
            {"action": "duplicate_ccw_estimate", "estimate_id": estimate_id, "new_name": new_name}
        )
    return client.duplicate_estimate(estimate_id, new_name).model_dump()
