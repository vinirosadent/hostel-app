"""
Field-level comment service for review workflows on fundraisers and events.
"""
from __future__ import annotations

from services.supabase_client import get_supabase


def list_comments(entity_type: str, entity_id: str, *,
                  only_unresolved: bool = False) -> list[dict]:
    sb = get_supabase()
    q = sb.table("entity_comments").select(
        "*, author:users!entity_comments_author_id_fkey(full_name, username)"
    ).eq("entity_type", entity_type).eq("entity_id", entity_id)
    if only_unresolved:
        q = q.eq("resolved", False)
    return q.order("created_at").execute().data or []


def comments_by_field(entity_type: str, entity_id: str) -> dict[str, list[dict]]:
    rows = list_comments(entity_type, entity_id)
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["field_path"], []).append(r)
    return out


def add_comment(entity_type: str, entity_id: str, *,
                field_path: str, comment_text: str,
                author_id: str, review_round: int = 1) -> dict:
    if not comment_text.strip():
        raise ValueError("Comment text cannot be empty.")
    sb = get_supabase()
    payload = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "field_path": field_path,
        "author_id": author_id,
        "comment_text": comment_text.strip(),
        "review_round": review_round,
    }
    res = sb.table("entity_comments").insert(payload).execute()
    return res.data[0]


def resolve_comment(comment_id: str, *, user_id: str,
                    resolution_note: str | None = None) -> dict:
    sb = get_supabase()
    res = sb.table("entity_comments").update({
        "resolved": True,
        "resolved_at": "now()",
        "resolved_by_id": user_id,
        "resolution_note": resolution_note,
    }).eq("id", comment_id).execute()
    return res.data[0] if res.data else {}


def unresolve_comment(comment_id: str) -> dict:
    sb = get_supabase()
    res = sb.table("entity_comments").update({
        "resolved": False,
        "resolved_at": None,
        "resolved_by_id": None,
    }).eq("id", comment_id).execute()
    return res.data[0] if res.data else {}


def count_unresolved(entity_type: str, entity_id: str) -> int:
    return len(list_comments(entity_type, entity_id, only_unresolved=True))
