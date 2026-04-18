"""
Compliance service: dynamic checklist of statements a student must confirm
before submitting, and tracking of what has been confirmed per entity.
"""
from __future__ import annotations

from services.supabase_client import get_supabase


def list_statements(entity_type: str) -> list[dict]:
    sb = get_supabase()
    return sb.table("compliance_statements").select("*").eq(
        "entity_type", entity_type
    ).eq("active", True).order("sort_order").execute().data or []


def list_confirmations(entity_type: str, entity_id: str) -> list[dict]:
    sb = get_supabase()
    return sb.table("compliance_confirmations").select("*").eq(
        "entity_type", entity_type
    ).eq("entity_id", entity_id).execute().data or []


def confirmed_statement_ids(entity_type: str, entity_id: str,
                            user_id: str | None = None) -> set[str]:
    rows = list_confirmations(entity_type, entity_id)
    if user_id:
        rows = [r for r in rows if r["confirmed_by_id"] == user_id]
    return {r["statement_id"] for r in rows}


def confirm(entity_type: str, entity_id: str,
            statement_id: str, user_id: str) -> None:
    sb = get_supabase()
    sb.table("compliance_confirmations").upsert(
        {
            "statement_id": statement_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "confirmed_by_id": user_id,
        },
        on_conflict="statement_id,entity_type,entity_id,confirmed_by_id",
    ).execute()


def unconfirm(entity_type: str, entity_id: str,
              statement_id: str, user_id: str) -> None:
    sb = get_supabase()
    sb.table("compliance_confirmations").delete().eq(
        "statement_id", statement_id
    ).eq("entity_type", entity_type).eq(
        "entity_id", entity_id
    ).eq("confirmed_by_id", user_id).execute()


def all_required_confirmed(entity_type: str, entity_id: str) -> bool:
    statements = list_statements(entity_type)
    required_ids = {s["id"] for s in statements if s["required"]}
    if not required_ids:
        return True
    confirmed = confirmed_statement_ids(entity_type, entity_id)
    return required_ids.issubset(confirmed)
