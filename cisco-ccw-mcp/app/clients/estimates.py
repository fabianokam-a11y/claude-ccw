"""
CiscoEstimateClient: Manage Estimate Web Services (createEstimate,
updateEstimate, acquireEstimate, listEstimate, deleteEstimate*).

Diferente do catálogo/preço, esta API é SOAP/XML (solução B2B-3.0), não
REST/JSON. Este client:
  - monta o envelope XML mínimo necessário
  - envia via POST com Content-Type application/xml
  - faz parse da resposta XML para os models Pydantic

*delete/duplicate: a doc pública "Manage Estimate Web Services" cobre
create/update/acquire/list. Copy (duplicar) existe na Xpress Connect mas o
nome exato do endpoint deve ser confirmado na doc do seu app antes do
primeiro uso real — deixei o método implementado seguindo o mesmo padrão
dos demais, mas SINALIZADO como não validado.

MODO DRY RUN: quando settings.ccw_dry_run é True, os métodos de escrita
(create/update/remove/delete/duplicate) NÃO enviam a requisição — apenas
retornam o XML/payload que seria enviado, dentro de Estimate(dry_run=True).
"""
from __future__ import annotations

from typing import Optional
from xml.etree import ElementTree as ET

from app.clients.commerce import CiscoBaseClient
from app.config import Settings
from app.models.estimate import Estimate, EstimateItem, EstimateItemInput

NS = {"est": "http://www.cisco.com/commerce/estimate"}  # placeholder, confirmar no WSDL do seu app

CREATE_PATH = "/commerce/EST/v2/async/createEstimate"
UPDATE_PATH = "/commerce/EST/v2/async/updateEstimate"
ACQUIRE_PATH = "/commerce/EST/v2/async/acquireEstimate"
LIST_PATH = "/commerce/EST/v2/async/listEstimate"
DELETE_PATH = "/commerce/EST/v2/async/deleteEstimate"  # não validado — confirmar
COPY_PATH = "/commerce/EST/v2/async/copyEstimate"  # não validado — confirmar


class CiscoEstimateClient:
    def __init__(self, base: CiscoBaseClient, settings: Settings):
        self._base = base
        self._settings = settings
        self._commerce_base_url = settings.cisco_commerce_base_url.rstrip("/")

    # ---------- construção de XML ----------

    @staticmethod
    def _build_estimate_xml(name: str, items: list[EstimateItemInput], estimate_id: Optional[str] = None) -> str:
        root = ET.Element("Estimate")
        if estimate_id:
            ET.SubElement(root, "EstimateId").text = estimate_id
        ET.SubElement(root, "EstimateName").text = name
        items_el = ET.SubElement(root, "Items")
        for item in items:
            item_el = ET.SubElement(items_el, "Item")
            ET.SubElement(item_el, "SKU").text = item.sku
            ET.SubElement(item_el, "Quantity").text = str(item.quantity)
        return ET.tostring(root, encoding="unicode")

    # ---------- operações de leitura ----------

    def get_estimate(self, estimate_id: str) -> Estimate:
        xml_body = f"<AcquireEstimateRequest><EstimateId>{estimate_id}</EstimateId></AcquireEstimateRequest>"
        resp = self._base.request(
            "POST",
            f"{self._commerce_base_url}{ACQUIRE_PATH}",
            tool="get_ccw_estimate",
            content=xml_body,
            headers={"Content-Type": "application/xml", "Accept": "application/xml"},
        )
        return self._parse_estimate_xml(resp.text)

    def list_estimates(
        self,
        limit: Optional[int] = None,
        status: Optional[str] = None,
        created_after: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[Estimate]:
        filters = []
        if status:
            filters.append(f"<Status>{status}</Status>")
        if created_after:
            filters.append(f"<CreatedAfter>{created_after}</CreatedAfter>")
        if search:
            filters.append(f"<Search>{search}</Search>")
        if limit:
            filters.append(f"<Limit>{limit}</Limit>")
        xml_body = f"<ListEstimateRequest>{''.join(filters)}</ListEstimateRequest>"

        resp = self._base.request(
            "POST",
            f"{self._commerce_base_url}{LIST_PATH}",
            tool="list_ccw_estimates",
            content=xml_body,
            headers={"Content-Type": "application/xml", "Accept": "application/xml"},
        )
        root = ET.fromstring(resp.text)
        return [self._parse_estimate_element(el) for el in root.findall(".//Estimate")]

    # ---------- operações de escrita (respeitam CCW_DRY_RUN) ----------

    def create_estimate(self, name: str, items: list[EstimateItemInput]) -> Estimate:
        xml_body = self._build_estimate_xml(name, items)

        if self._settings.ccw_dry_run:
            return Estimate(
                name=name,
                status="DRY_RUN — nada foi enviado ao CCW",
                items=[EstimateItem(sku=i.sku, quantity=i.quantity) for i in items],
                dry_run=True,
                raw={"would_send_xml": xml_body, "endpoint": CREATE_PATH},
            )

        resp = self._base.request(
            "POST",
            f"{self._commerce_base_url}{CREATE_PATH}",
            tool="create_ccw_estimate",
            content=xml_body,
            headers={"Content-Type": "application/xml", "Accept": "application/xml"},
        )
        return self._parse_estimate_xml(resp.text)

    def add_or_update_item(self, estimate_id: str, sku: str, quantity: int) -> Estimate:
        xml_body = self._build_estimate_xml(
            name="", items=[EstimateItemInput(sku=sku, quantity=quantity)], estimate_id=estimate_id
        )
        if self._settings.ccw_dry_run:
            return Estimate(
                estimate_id=estimate_id,
                name="(dry-run)",
                status="DRY_RUN — nada foi enviado ao CCW",
                items=[EstimateItem(sku=sku, quantity=quantity)],
                dry_run=True,
                raw={"would_send_xml": xml_body, "endpoint": UPDATE_PATH},
            )
        resp = self._base.request(
            "POST",
            f"{self._commerce_base_url}{UPDATE_PATH}",
            tool="update_ccw_estimate_item",
            content=xml_body,
            headers={"Content-Type": "application/xml", "Accept": "application/xml"},
        )
        return self._parse_estimate_xml(resp.text)

    def remove_item(self, estimate_id: str, sku: str) -> Estimate:
        xml_body = (
            f"<UpdateEstimateRequest><EstimateId>{estimate_id}</EstimateId>"
            f"<RemoveItems><SKU>{sku}</SKU></RemoveItems></UpdateEstimateRequest>"
        )
        if self._settings.ccw_dry_run:
            return Estimate(
                estimate_id=estimate_id,
                name="(dry-run)",
                status="DRY_RUN — nada foi enviado ao CCW",
                dry_run=True,
                raw={"would_send_xml": xml_body, "endpoint": UPDATE_PATH},
            )
        resp = self._base.request(
            "POST",
            f"{self._commerce_base_url}{UPDATE_PATH}",
            tool="remove_ccw_estimate_item",
            content=xml_body,
            headers={"Content-Type": "application/xml", "Accept": "application/xml"},
        )
        return self._parse_estimate_xml(resp.text)

    def delete_estimate(self, estimate_id: str) -> dict:
        xml_body = f"<DeleteEstimateRequest><EstimateId>{estimate_id}</EstimateId></DeleteEstimateRequest>"
        if self._settings.ccw_dry_run:
            return {"dry_run": True, "would_send_xml": xml_body, "endpoint": DELETE_PATH}
        resp = self._base.request(
            "POST",
            f"{self._commerce_base_url}{DELETE_PATH}",
            tool="delete_ccw_estimate",
            content=xml_body,
            headers={"Content-Type": "application/xml", "Accept": "application/xml"},
        )
        return {"dry_run": False, "status_code": resp.status_code}

    def duplicate_estimate(self, estimate_id: str, new_name: str) -> Estimate:
        xml_body = (
            f"<CopyEstimateRequest><EstimateId>{estimate_id}</EstimateId>"
            f"<NewEstimateName>{new_name}</NewEstimateName></CopyEstimateRequest>"
        )
        if self._settings.ccw_dry_run:
            return Estimate(
                name=new_name,
                status="DRY_RUN — nada foi enviado ao CCW",
                dry_run=True,
                raw={"would_send_xml": xml_body, "endpoint": COPY_PATH},
            )
        resp = self._base.request(
            "POST",
            f"{self._commerce_base_url}{COPY_PATH}",
            tool="duplicate_ccw_estimate",
            content=xml_body,
            headers={"Content-Type": "application/xml", "Accept": "application/xml"},
        )
        return self._parse_estimate_xml(resp.text)

    # ---------- parsing ----------

    def _parse_estimate_xml(self, xml_text: str) -> Estimate:
        root = ET.fromstring(xml_text)
        el = root.find(".//Estimate")
        if el is None:
            el = root  # algumas respostas já vêm com Estimate como raiz
        return self._parse_estimate_element(el)

    @staticmethod
    def _parse_estimate_element(el: ET.Element) -> Estimate:
        def text(tag: str) -> Optional[str]:
            found = el.find(tag)
            return found.text if found is not None else None

        items = []
        for item_el in el.findall(".//Item"):
            sku = item_el.findtext("SKU", default="")
            qty = int(item_el.findtext("Quantity", default="0") or 0)
            unit_price_txt = item_el.findtext("UnitPrice")
            unit_price = float(unit_price_txt) if unit_price_txt else None
            items.append(
                EstimateItem(
                    sku=sku,
                    description=item_el.findtext("Description"),
                    quantity=qty,
                    unit_price=unit_price,
                    total_price=(unit_price * qty) if unit_price is not None else None,
                )
            )

        subtotal_txt = text("Subtotal")
        total_txt = text("Total")
        return Estimate(
            estimate_id=text("EstimateId"),
            name=text("EstimateName") or "",
            status=text("Status"),
            items=items,
            subtotal=float(subtotal_txt) if subtotal_txt else None,
            total=float(total_txt) if total_txt else None,
            currency=text("Currency") or "USD",
            created_date=text("CreatedDate"),
            ccw_url=text("CCWUrl"),
            dry_run=False,
        )
