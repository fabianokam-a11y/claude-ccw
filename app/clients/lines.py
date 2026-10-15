"""
Montagem de linhas no formato do Cisco Commerce GraphQL (EstimateLineInput).

Formato interno de item (portado dos helpers do time):
  {"sku", "qty", "parent" (índice 1-based, 0 = raiz), "dur" (meses),
   "disc", "sel", "path", "hash", "term", "extra"}
"""
from __future__ import annotations

from datetime import datetime

ZERO_UUID = "00000000-0000-0000-0000-000000000000"
CURRENCY_BY_PRICE_LIST = {"GLBRL": "BRL", "GLICON": "USD", "GLUS": "USD"}


def now_local() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def build_lines(items: list[dict]) -> list[dict]:
    out = []
    for i, it in enumerate(items, 1):
        cfg = {"selectedBy": it.get("sel") or "USER"}
        if it.get("path"):
            cfg["path"] = it["path"]
        if it.get("hash"):
            cfg["hashKey"] = it["hash"]
        line = {
            "configurationLineReferenceInput": {"lineId": i, "parentLineId": it.get("parent", 0)},
            "configurationDetailsInput": cfg,
            "quantity": {"measurement": it["qty"]},
            "item": {"sku": it["sku"]},
        }
        if it.get("dur"):
            line["duration"] = {"measurement": it["dur"]}
        if it.get("term"):
            line["initialTerm"] = {"measurement": it["term"]}
        line.update(it.get("extra") or {})
        entry = {"line": line}
        if it.get("disc"):
            entry["discount"] = {"discountRate": {"measurement": it["disc"]}}
        out.append(entry)
    return out


def drop_items(items: list[dict], skus: set[str]) -> list[dict]:
    """Remove linhas cujo SKU está em `skus`; filhos sobem para o avô."""
    idx = {i: it for i, it in enumerate(items, 1)}
    removed = {i for i, it in idx.items() if it["sku"] in skus}

    def up(p: int) -> int:
        while p in removed:
            p = idx[p]["parent"]
        return p

    kept = [i for i in idx if i not in removed]
    remap = {old: new for new, old in enumerate(kept, 1)}
    out = []
    for old in kept:
        it = dict(idx[old])
        p = up(it["parent"]) if it["parent"] else 0
        it["parent"] = remap.get(p, 0) if p else 0
        out.append(it)
    return out
