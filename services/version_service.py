"""
Version snapshots plus structured diffs used by the review workflow.
A submission captures a full snapshot; a resubmission captures another;
the UI can diff them to show only what changed.
"""
from __future__ import annotations

from typing import Any

from services.supabase_client import get_supabase


def build_snapshot(fundraiser_data: dict, items: list[dict],
                   selling_options: list[dict]) -> dict:
    def pick_fr(fr: dict) -> dict:
        keep = {
            "name", "objective", "marketing_start", "marketing_end",
            "ordering_start", "ordering_end", "supplier_order_date",
            "delivery_date", "flyer_removal_date", "flyer_remover_name",
            "marketing_plan", "rf_in_charge_id", "committee_chair_id",
            "proposal_extra",
        }
        return {k: fr.get(k) for k in keep}

    def pick_item(it: dict) -> dict:
        return {
            "item_code": it["item_code"],
            "item_name": it.get("item_name"),
            "supplier": it.get("supplier"),
            "quantity": it["quantity"],
            "unit_cost": float(it["unit_cost"]),
            "requires_quote": it["requires_quote"],
            "notes": it.get("notes"),
        }

    def pick_option(o: dict) -> dict:
        return {
            "option_name": o["option_name"],
            "option_type": o["option_type"],
            "composition": o.get("composition") or {},
            "selling_price": float(o["selling_price"]),
        }

    return {
        "fundraiser": pick_fr(fundraiser_data),
        "items": sorted([pick_item(i) for i in items],
                        key=lambda x: x["item_code"]),
        "selling_options": sorted(
            [pick_option(o) for o in selling_options],
            key=lambda x: (x["option_type"], x["option_name"]),
        ),
    }


def save_version(entity_type: str, entity_id: str, *,
                 snapshot: dict, submitted_by_id: str,
                 submission_note: str | None = None) -> dict:
    sb = get_supabase()
    latest = sb.table("entity_versions").select("version_number").eq(
        "entity_type", entity_type
    ).eq("entity_id", entity_id).order(
        "version_number", desc=True
    ).limit(1).execute().data
    next_num = (latest[0]["version_number"] + 1) if latest else 1
    payload = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "version_number": next_num,
        "snapshot": snapshot,
        "submitted_by_id": submitted_by_id,
        "submission_note": submission_note,
    }
    res = sb.table("entity_versions").insert(payload).execute()
    return res.data[0]


def latest_version(entity_type: str, entity_id: str) -> dict | None:
    sb = get_supabase()
    res = sb.table("entity_versions").select("*").eq(
        "entity_type", entity_type
    ).eq("entity_id", entity_id).order(
        "version_number", desc=True
    ).limit(1).execute()
    return res.data[0] if res.data else None


def _diff_scalar(path: str, before: Any, after: Any, out: list[dict]) -> None:
    if before != after:
        out.append({"path": path, "before": before, "after": after})


def _diff_dict(prefix: str, before: dict, after: dict,
               out: list[dict]) -> None:
    keys = set(before) | set(after)
    for k in keys:
        path = f"{prefix}.{k}" if prefix else k
        b, a = before.get(k), after.get(k)
        if isinstance(b, dict) or isinstance(a, dict):
            _diff_dict(path, b or {}, a or {}, out)
        elif isinstance(b, list) or isinstance(a, list):
            _diff_list(path, b or [], a or [], out)
        else:
            _diff_scalar(path, b, a, out)


def _diff_list(prefix: str, before: list, after: list,
               out: list[dict]) -> None:
    def key_of(row: Any) -> Any:
        if isinstance(row, dict):
            return row.get("item_code") or row.get("option_name") or id(row)
        return row
    before_map = {key_of(x): x for x in before}
    after_map = {key_of(x): x for x in after}
    all_keys = sorted(set(before_map) | set(after_map), key=lambda k: str(k))
    for k in all_keys:
        b = before_map.get(k)
        a = after_map.get(k)
        path = f"{prefix}[{k}]"
        if b is None:
            out.append({"path": path, "before": None, "after": a,
                        "kind": "added"})
        elif a is None:
            out.append({"path": path, "before": b, "after": None,
                        "kind": "removed"})
        elif isinstance(b, dict) and isinstance(a, dict):
            _diff_dict(path, b, a, out)
        else:
            _diff_scalar(path, b, a, out)


def diff_snapshots(before: dict, after: dict) -> list[dict]:
    out: list[dict] = []
    _diff_dict("", before or {}, after or {}, out)
    return out
