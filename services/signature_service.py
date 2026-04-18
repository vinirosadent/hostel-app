"""
Electronic signature service: audit-grade record that a user typed a
signature string for a specific purpose on a specific entity at a timestamp.
Not cryptographic PKI; sufficient for internal governance.
"""
from __future__ import annotations

from services.supabase_client import get_supabase


def list_required_signatures(entity_type: str, document_type: str) -> list[dict]:
    sb = get_supabase()
    return sb.table("signatory_requirements").select("*").eq(
        "entity_type", entity_type
    ).eq("document_type", document_type).eq("active", True).order(
        "sort_order"
    ).execute().data or []


def list_signatures(entity_type: str, entity_id: str) -> list[dict]:
    sb = get_supabase()
    return sb.table("signatures").select(
        "*, signer:users!signatures_signer_id_fkey(full_name, username)"
    ).eq("entity_type", entity_type).eq("entity_id", entity_id).order(
        "signed_at"
    ).execute().data or []


def sign(*, entity_type: str, entity_id: str, signer_id: str,
         signer_role_code: str, signer_name_snap: str,
         signature_text: str, purpose: str) -> dict:
    if not signature_text.strip():
        raise ValueError("Signature text cannot be empty.")
    if len(signature_text) > 100:
        raise ValueError("Signature text too long (max 100 chars).")
    sb = get_supabase()
    payload = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "signer_id": signer_id,
        "signer_role_code": signer_role_code,
        "signer_name_snap": signer_name_snap,
        "signature_text": signature_text.strip(),
        "purpose": purpose,
    }
    res = sb.table("signatures").upsert(
        payload, on_conflict="entity_type,entity_id,signer_id,purpose"
    ).execute()
    return res.data[0]


def signature_status(entity_type: str, entity_id: str,
                     document_type: str) -> list[dict]:
    reqs = list_required_signatures(entity_type, document_type)
    sigs = list_signatures(entity_type, entity_id)
    sigs_by_purpose = {s["purpose"]: s for s in sigs}
    out = []
    for r in reqs:
        s = sigs_by_purpose.get(r["purpose_code"])
        out.append({**r, "signed_by": s})
    return out


def all_required_signed(entity_type: str, entity_id: str,
                        document_type: str) -> bool:
    status = signature_status(entity_type, entity_id, document_type)
    return all(row["signed_by"] is not None
               for row in status if row.get("is_required"))
