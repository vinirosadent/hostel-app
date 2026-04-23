"""
Fundraiser service layer (v2).

Pure Python business logic — no Streamlit imports.
Terminology follows the standardised glossary:
  - Unit Cost          = cost per item to the committee
  - Total Cost         = unit cost × quantity purchased
  - Selling Price (before GST) = committee's price before tax
  - Final Customer Price (GST-inclusive) = selling price × 1.09
  - Gross Revenue (before GST) = total sales value excl. GST
  - GST Collected      = 9 % of gross revenue (government portion, NOT profit)
  - Gross Profit       = gross revenue – total cost
  - Net Amount Available = gross profit (committee keeps pre-GST revenue)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from services.supabase_client import get_supabase

STORAGE_BUCKET = "fundraiser-assets"

# ── Status constants ────────────────────────────────────────────────────────

VALID_STATUSES = [
    "draft", "rf_review", "master_review", "approved",
    "executing", "reporting",
    "rf_confirming", "finance_confirming", "master_confirming",
    "closed", "rejected",
]

# reporting → rf_confirming  means DOF has submitted their checklist closure
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft":              {"rf_review"},
    # RF sends to Master OR Master approves directly OR RF returns to student
    "rf_review":          {"master_review", "approved", "draft"},
    "master_review":      {"approved", "rf_review"},
    "approved":           {"executing"},
    "executing":          {"reporting"},
    # RF completes closure checklist → moves to DOF queue
    "reporting":          {"rf_confirming"},
    "rf_confirming":      {"finance_confirming"},
    "finance_confirming": {"master_confirming"},
    "master_confirming":  {"closed"},
    "closed":             set(),
    "rejected":           {"draft"},
}

STATUS_DISPLAY: dict[str, str] = {
    "draft":              "Draft",
    "rf_review":          "Submitted to RF",
    "master_review":      "Approved by RF – Awaiting Master",
    "approved":           "Approved for Execution",
    "executing":          "In Execution",
    "reporting":          "Reporting in Progress",
    "rf_confirming":      "Awaiting RF Confirmation",
    "finance_confirming": "Awaiting Finance Confirmation",
    "master_confirming":  "Awaiting Master Confirmation",
    "closed":             "Funds Available / Closed",
    "rejected":           "Returned – Action Required",
}

# Ordered for progress-bar rank computation
_STATUS_RANK: list[str] = [
    "draft", "rejected", "rf_review", "master_review",
    "approved", "executing", "reporting",
    "rf_confirming", "finance_confirming", "master_confirming", "closed",
]

RF_CHECKLIST_ITEMS: dict[str, str] = {
    "stock_accounted":    "All items purchased have been accounted for in the stock movement records.",
    "sales_recorded":     "All selling options and quantities sold are correctly recorded.",
    "unsold_noted":       "Any unsold items and remaining stock have been noted.",
    "financial_reviewed": "The financial summary has been reviewed and verified as accurate.",
    "nusync_only":        "All customer payments were collected exclusively through NUSync.",
    "no_personal_accts":  "No funds were collected through personal accounts or third-party transfers.",
    "flyers_removed":     "Marketing materials and flyers have been removed from all public areas by the stated removal date.",
    "gst_acknowledged":   (
        "The Committee acknowledges that GST collected from customers is not part of Committee "
        "profit — it is remitted to the government. The amount available to the Committee is the "
        "Gross Revenue before GST minus Total Cost."
    ),
}

DOF_CHECKLIST_ITEMS: dict[str, str] = {
    "reimbursements_paid": (
        "All approved reimbursements have been paid out to the students "
        "who advanced money for this fundraiser."
    ),
    "suppliers_paid": (
        "All suppliers listed in the Items table have been paid in full, "
        "with no outstanding invoices."
    ),
    "variances_documented": (
        "Any difference between expected and actual income or expenses "
        "has been documented in the Report section, with reasons provided."
    ),
    "receipts_archived": (
        "All purchase receipts and PayNow payment records have been "
        "uploaded to the Appendix and are legible."
    ),
}

FINANCE_CHECKLIST_ITEMS: dict[str, str] = {
    "revenue_matches_nusync": (
        "The declared Gross Revenue matches the amount deposited in NUSync "
        "for this fundraiser. Any discrepancy has been investigated and "
        "resolved."
    ),
    "gst_remitted": (
        "The 9% GST collected from customers has been accounted for and "
        "will be remitted to the government through the Finance Office, "
        "separately from the Committee's profit."
    ),
    "ledger_updated": (
        "The fundraiser entry has been posted to the Hall's financial "
        "ledger with the correct cost centre and period."
    ),
}

MASTER_CHECKLIST_ITEMS: dict[str, str] = {
    "executed_per_approved": (
        "The fundraiser was carried out according to the approved "
        "proposal. Any deviations have been documented and justified."
    ),
    "fully_closed": (
        "The fundraiser is fully closed — no outstanding payments, no "
        "unreconciled stock, and no pending issues requiring action."
    ),
    "funds_release_authorised": (
        "I authorise the release of the net profit (Gross Revenue − "
        "Total Cost) to the Committee's account."
    ),
}


# ── Exceptions ──────────────────────────────────────────────────────────────

class FundraiserError(Exception):
    pass


class InvalidTransition(FundraiserError):
    pass


class ValidationError(FundraiserError):
    pass


def check_transition(current: str, new: str) -> None:
    if new not in ALLOWED_TRANSITIONS.get(current, set()):
        cur_label = STATUS_DISPLAY.get(current, current)
        new_label = STATUS_DISPLAY.get(new, new)
        raise InvalidTransition(
            f"Cannot transition from '{cur_label}' to '{new_label}'."
        )


def status_rank(s: str) -> int:
    try:
        return _STATUS_RANK.index(s)
    except ValueError:
        return 0


# ── Financial model ─────────────────────────────────────────────────────────

@dataclass
class FinancialSummary:
    total_cost:               Decimal = Decimal("0")
    gross_revenue_before_gst: Decimal = Decimal("0")
    gst_collected:            Decimal = Decimal("0")
    total_customer_payment:   Decimal = Decimal("0")
    gross_profit:             Decimal = Decimal("0")
    max_possible_revenue:     Decimal = Decimal("0")

    def as_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.__dict__.items()}


@dataclass
class StockRow:
    item_code: str
    item_name: str = ""
    purchased: int = 0
    sold: int = 0

    @property
    def unsold(self) -> int:
        return self.purchased - self.sold

    @property
    def over_sold(self) -> bool:
        return self.sold > self.purchased


# ── App settings ─────────────────────────────────────────────────────────────

def _settings() -> dict[str, Any]:
    sb = get_supabase()
    rows = sb.table("app_settings").select("key,value").execute().data or []
    return {r["key"]: r["value"] for r in rows}


def get_gst_rate() -> Decimal:
    return Decimal(str(_settings().get("gst_rate", 0.09)))


def get_min_margin() -> Decimal:
    """Minimum acceptable profit % = (selling_price - unit_cost) / unit_cost."""
    return Decimal(str(_settings().get("min_profit_margin", 0.20)))


def get_quote_threshold() -> Decimal:
    return Decimal(str(_settings().get("quote_threshold", 1000)))


def get_currency() -> str:
    return _settings().get("currency", "SGD")


# ── Fundraiser CRUD ──────────────────────────────────────────────────────────

def list_fundraisers(status: str | None = None) -> list[dict]:
    sb = get_supabase()
    q = sb.table("fundraisers").select("*").is_("deleted_at", "null")
    if status:
        q = q.eq("status", status)
    return q.order("created_at", desc=True).execute().data or []


def get_fundraiser(fundraiser_id: str) -> dict | None:
    sb = get_supabase()
    res = sb.table("fundraisers").select("*").eq("id", fundraiser_id).execute()
    return res.data[0] if res.data else None


def create_fundraiser(*, name: str, created_by_id: str,
                      rf_in_charge_id: str, objective: str | None = None,
                      committee_chair_id: str | None = None) -> dict:
    if not name.strip():
        raise ValidationError("Fundraiser name is required.")
    sb = get_supabase()
    payload = {
        "name": name.strip(),
        "objective": objective,
        "status": "draft",
        "rf_in_charge_id": rf_in_charge_id,
        "committee_chair_id": committee_chair_id,
        "created_by_id": created_by_id,
    }
    res = sb.table("fundraisers").insert(payload).execute()
    return res.data[0]


_UPDATABLE_FIELDS = {
    "name", "objective", "beneficiary",
    "proposal_prepared_by", "on_behalf_of",
    "rf_in_charge_id", "committee_chair_id",
    "marketing_start", "marketing_end",
    "ordering_start", "ordering_end",
    "supplier_order_date", "delivery_date",
    "flyer_removal_date", "flyer_remover_name",
    "report_submission_deadline",
    "marketing_plan", "proposal_extra", "report_extra",
    # compliance (page 1)
    "compliance_nusync", "compliance_no_intermediary",
    "compliance_gst_artwork", "compliance_regulations",
    # RF closure checklist
    "rf_checklist",
    "dof_checklist",
    "finance_checklist",
    "master_checklist",
}


def update_fundraiser_fields(fundraiser_id: str, fields: dict) -> dict:
    clean = {k: v for k, v in fields.items() if k in _UPDATABLE_FIELDS}
    if not clean:
        return get_fundraiser(fundraiser_id) or {}
    sb = get_supabase()
    res = sb.table("fundraisers").update(clean).eq("id", fundraiser_id).execute()
    return res.data[0] if res.data else {}


def validate_for_submission(fr: dict) -> list[str]:
    """Return validation errors preventing RF submission. Empty = OK."""
    errors: list[str] = []
    if not (fr.get("name") or "").strip():
        errors.append("Project name is required.")
    if not (fr.get("objective") or "").strip():
        errors.append("Project description is required.")
    if not (fr.get("proposal_prepared_by") or "").strip():
        errors.append("Proposal prepared by is required.")
    if not (fr.get("on_behalf_of") or "").strip():
        errors.append("Committee/Activity (on behalf of) is required.")
    if not fr.get("delivery_date"):
        errors.append("Expected delivery / closing date is required.")
    for key, label in [
        ("compliance_nusync",         "All funds collected via NUSync only"),
        ("compliance_no_intermediary", "No personal account intermediaries"),
        ("compliance_gst_artwork",    "GST statement on all marketing artwork"),
        ("compliance_regulations",    "NUS regulations acknowledgement"),
    ]:
        if not fr.get(key):
            errors.append(f"Compliance checkbox required: {label}.")
    return errors


def transition_status(fundraiser_id: str, new_status: str,
                      by_user: dict | None = None) -> dict:
    """Transition status and auto-stamp relevant timestamp + signature fields."""
    fr = get_fundraiser(fundraiser_id)
    if not fr:
        raise ValidationError("Fundraiser not found.")
    check_transition(fr["status"], new_status)
    now = datetime.now(tz=timezone.utc).isoformat()
    user_name: str = (by_user or {}).get("full_name", "")
    extra: dict[str, Any] = {}

    if new_status == "rf_review":
        extra["submitted_at"] = now
        extra["submitted_by_name"] = user_name
    elif new_status == "master_review":
        extra["rf_approved_at"] = now
        extra["rf_approved_by"] = user_name
    elif new_status == "approved":
        extra["master_approved_at"] = now
        extra["master_approved_by"] = user_name
    elif new_status == "rf_confirming":
        # DOF has completed closure checklist (first signer)
        extra["dof_confirmed_at"] = now
        extra["dof_confirmed_by"] = user_name
    elif new_status == "finance_confirming":
        # RF has completed closure checklist (second signer)
        extra["rf_confirmed_at"] = now
        extra["rf_confirmed_by"] = user_name
    elif new_status == "master_confirming":
        extra["finance_confirmed_at"] = now
        extra["finance_confirmed_by"] = user_name
    elif new_status == "closed":
        extra["master_closure_at"] = now
        extra["master_closure_by"] = user_name
        extra["funds_available"] = True

    sb = get_supabase()
    res = sb.table("fundraisers").update(
        {"status": new_status, **extra}
    ).eq("id", fundraiser_id).execute()
    return res.data[0]


# ── Items ────────────────────────────────────────────────────────────────────

def list_items(fundraiser_id: str) -> list[dict]:
    sb = get_supabase()
    return sb.table("fundraiser_items").select("*").eq(
        "fundraiser_id", fundraiser_id
    ).order("item_code").execute().data or []


def upsert_item(fundraiser_id: str, item_code: str, *,
                item_name: str | None = None,
                supplier: str | None = None,
                quantity: int = 0,
                unit_cost: float = 0.0,
                notes: str | None = None) -> dict:
    if not item_code.strip():
        raise ValidationError("Item code is required.")
    if quantity <= 0:
        raise ValidationError("Quantity must be greater than zero.")
    if unit_cost < 0:
        raise ValidationError("Unit cost must be non-negative.")
    sb = get_supabase()
    threshold = float(get_quote_threshold())
    requires_quote = (quantity * unit_cost) >= threshold
    payload = {
        "fundraiser_id": fundraiser_id,
        "item_code": item_code.strip().upper(),
        "item_name": item_name,
        "supplier": supplier,
        "quantity": int(quantity),
        "unit_cost": float(unit_cost),
        "requires_quote": requires_quote,
        "notes": notes,
    }
    res = sb.table("fundraiser_items").upsert(
        payload, on_conflict="fundraiser_id,item_code"
    ).execute()
    return res.data[0]


def delete_item(item_id: str) -> None:
    get_supabase().table("fundraiser_items").delete().eq("id", item_id).execute()


# ── Selling options ──────────────────────────────────────────────────────────

def list_selling_options(fundraiser_id: str) -> list[dict]:
    sb = get_supabase()
    return sb.table("fundraiser_selling_options").select("*").eq(
        "fundraiser_id", fundraiser_id
    ).order("option_type").order("option_name").execute().data or []


def _compute_unit_cost_from_composition(
    composition: dict[str, int], items: list[dict]
) -> Decimal:
    by_code = {it["item_code"]: Decimal(str(it["unit_cost"])) for it in items}
    total = Decimal("0")
    for code, qty in composition.items():
        if code not in by_code:
            raise ValidationError(f"Unknown item code in composition: {code}")
        total += by_code[code] * Decimal(str(qty))
    return total


def upsert_selling_option(fundraiser_id: str, option_name: str, *,
                           option_type: str,
                           composition: dict[str, int],
                           selling_price: float,
                           option_id: str | None = None) -> dict:
    if option_type not in ("single", "bundle"):
        raise ValidationError("option_type must be 'single' or 'bundle'.")
    if not composition:
        raise ValidationError("Composition cannot be empty.")
    if any(int(v) < 1 for v in composition.values()):
        raise ValidationError("All composition quantities must be ≥ 1.")
    if option_type == "single" and len(composition) != 1:
        raise ValidationError("A 'single' option must reference exactly one item.")
    if option_type == "bundle" and len(composition) < 2:
        raise ValidationError("A combo must include at least 2 different items.")

    items = list_items(fundraiser_id)
    unit_cost = _compute_unit_cost_from_composition(composition, items)
    price_dec = Decimal(str(selling_price))
    min_margin = get_min_margin()
    # Profit % = (selling_price - unit_cost) / unit_cost  (per spec)
    profit = price_dec - unit_cost
    profit_pct = (profit / unit_cost) if unit_cost > 0 else Decimal("0")
    is_acceptable = bool(profit_pct >= min_margin)

    payload = {
        "fundraiser_id": fundraiser_id,
        "option_name": option_name.strip(),
        "option_type": option_type,
        "composition": composition,
        "unit_cost": float(unit_cost),
        "selling_price": float(selling_price),
        "is_acceptable": is_acceptable,
    }
    sb = get_supabase()
    if option_id:
        res = sb.table("fundraiser_selling_options").update(payload).eq(
            "id", option_id
        ).execute()
    else:
        res = sb.table("fundraiser_selling_options").upsert(
            payload, on_conflict="fundraiser_id,option_name"
        ).execute()
    return res.data[0]


def delete_selling_option(option_id: str) -> None:
    get_supabase().table("fundraiser_selling_options").delete().eq(
        "id", option_id
    ).execute()


# ── Stock movements ──────────────────────────────────────────────────────────

def list_stock_movements(fundraiser_id: str) -> list[dict]:
    sb = get_supabase()
    return sb.table("fundraiser_stock_movements").select("*").eq(
        "fundraiser_id", fundraiser_id
    ).execute().data or []


def upsert_stock_movement(fundraiser_id: str, selling_option_id: str,
                           quantity_sold: int) -> dict:
    if quantity_sold < 0:
        raise ValidationError("quantity_sold must be non-negative.")
    sb = get_supabase()
    payload = {
        "fundraiser_id": fundraiser_id,
        "selling_option_id": selling_option_id,
        "quantity_sold": int(quantity_sold),
    }
    res = sb.table("fundraiser_stock_movements").upsert(
        payload, on_conflict="selling_option_id"
    ).execute()
    return res.data[0]


def compute_stock_reconciliation(fundraiser_id: str) -> list[StockRow]:
    items = {it["item_code"]: it for it in list_items(fundraiser_id)}
    options = {o["id"]: o for o in list_selling_options(fundraiser_id)}
    movements = list_stock_movements(fundraiser_id)
    rows: dict[str, StockRow] = {
        code: StockRow(
            item_code=code,
            item_name=it.get("item_name") or code,
            purchased=int(it["quantity"]),
        )
        for code, it in items.items()
    }
    for mv in movements:
        opt = options.get(mv["selling_option_id"])
        if not opt:
            continue
        qty_sold = int(mv["quantity_sold"])
        for code, qty_in_opt in (opt.get("composition") or {}).items():
            if code not in rows:
                rows[code] = StockRow(item_code=code, purchased=0)
            rows[code].sold += qty_sold * int(qty_in_opt)
    return sorted(rows.values(), key=lambda r: r.item_code)


def compute_financial_summary(fundraiser_id: str) -> FinancialSummary:
    items = list_items(fundraiser_id)
    options = list_selling_options(fundraiser_id)
    movements = {
        m["selling_option_id"]: int(m["quantity_sold"])
        for m in list_stock_movements(fundraiser_id)
    }
    total_cost = sum(
        (Decimal(str(it["unit_cost"])) * Decimal(str(it["quantity"])) for it in items),
        Decimal("0"),
    )
    purchased_by_code = {it["item_code"]: int(it["quantity"]) for it in items}
    max_rev = Decimal("0")
    for opt in options:
        comp = opt.get("composition") or {}
        if not comp:
            continue
        try:
            max_units = min(
                purchased_by_code.get(code, 0) // int(qty)
                for code, qty in comp.items()
                if int(qty) > 0
            )
        except ValueError:
            max_units = 0
        max_rev += Decimal(str(opt["selling_price"])) * Decimal(max_units)

    # selling_price in DB is always BEFORE GST
    gross_rev = sum(
        (Decimal(str(o["selling_price"])) * Decimal(str(movements.get(o["id"], 0)))
         for o in options),
        Decimal("0"),
    )
    gst_rate = get_gst_rate()
    gst_collected = gross_rev * gst_rate
    total_customer_payment = gross_rev + gst_collected
    gross_profit = gross_rev - total_cost

    return FinancialSummary(
        total_cost=total_cost,
        gross_revenue_before_gst=gross_rev,
        gst_collected=gst_collected,
        total_customer_payment=total_customer_payment,
        gross_profit=gross_profit,
        max_possible_revenue=max_rev,
    )


# ── Assets (appendix uploads) ────────────────────────────────────────────────

def list_assets(fundraiser_id: str, section: str | None = None) -> list[dict]:
    sb = get_supabase()
    q = sb.table("fundraiser_assets").select("*").eq("fundraiser_id", fundraiser_id)
    if section:
        q = q.eq("section", section)
    return q.order("created_at").execute().data or []


def create_asset(fundraiser_id: str, *,
                 section: str,
                 asset_type: str,
                 title: str,
                 description: str | None,
                 file_name: str,
                 file_bytes: bytes,
                 file_mime: str | None,
                 linked_item_code: str | None,
                 created_by_id: str) -> dict:
    if section not in ("marketing", "artwork"):
        raise ValidationError("Section must be 'marketing' or 'artwork'.")
    if asset_type not in ("product_design", "marketing_promo", "other"):
        raise ValidationError("Invalid asset type.")
    if not title.strip():
        raise ValidationError("Title is required.")
    if not description or not description.strip():
        raise ValidationError("Description is required.")

    import uuid as _uuid
    sb = get_supabase()
    unique_name = f"{_uuid.uuid4().hex}_{file_name}"
    storage_path = f"{fundraiser_id}/{section}/{unique_name}"
    try:
        opts: dict[str, Any] = {"content-type": file_mime or "application/octet-stream"}
        sb.storage.from_(STORAGE_BUCKET).upload(storage_path, file_bytes, file_options=opts)
        file_url = sb.storage.from_(STORAGE_BUCKET).get_public_url(storage_path)
    except Exception as exc:
        raise FundraiserError(f"File upload to storage failed: {exc}") from exc

    payload = {
        "fundraiser_id": fundraiser_id,
        "section": section,
        "asset_type": asset_type,
        "title": title.strip(),
        "description": (description or "").strip() or None,
        "file_name": file_name,
        "file_url": file_url,
        "file_mime": file_mime,
        "linked_item_code": linked_item_code or None,
        "created_by_id": created_by_id,
    }
    res = sb.table("fundraiser_assets").insert(payload).execute()
    return res.data[0]


def update_asset_metadata(asset_id: str, *,
                           title: str | None = None,
                           description: str | None = None,
                           asset_type: str | None = None,
                           linked_item_code: str | None = None) -> dict:
    fields: dict[str, Any] = {}
    if title is not None:
        fields["title"] = title.strip()
    if description is not None:
        fields["description"] = description.strip()
    if asset_type is not None:
        fields["asset_type"] = asset_type
    if linked_item_code is not None:
        fields["linked_item_code"] = linked_item_code or None
    if not fields:
        res = get_supabase().table("fundraiser_assets").select("*").eq("id", asset_id).execute()
        return res.data[0] if res.data else {}
    res = get_supabase().table("fundraiser_assets").update(fields).eq("id", asset_id).execute()
    return res.data[0] if res.data else {}


def delete_asset(asset_id: str) -> None:
    sb = get_supabase()
    res = sb.table("fundraiser_assets").select("file_url").eq("id", asset_id).execute()
    if res.data:
        url: str = res.data[0].get("file_url", "")
        marker = f"/object/public/{STORAGE_BUCKET}/"
        if marker in url:
            storage_path = url.split(marker, 1)[1]
            try:
                sb.storage.from_(STORAGE_BUCKET).remove([storage_path])
            except Exception:
                pass
    sb.table("fundraiser_assets").delete().eq("id", asset_id).execute()


# ── Students / committee ─────────────────────────────────────────────────────

def register_student(fundraiser_id: str, user_id: str, *,
                     position: str = "member",
                     added_by_id: str | None = None) -> None:
    sb = get_supabase()
    payload: dict[str, Any] = {
        "fundraiser_id": fundraiser_id,
        "user_id": user_id,
        "position": position,
    }
    if added_by_id:
        payload["added_by"] = added_by_id
    sb.table("fundraiser_students").upsert(
        payload, on_conflict="fundraiser_id,user_id"
    ).execute()


def unregister_student(fundraiser_id: str, user_id: str) -> None:
    sb = get_supabase()
    sb.table("fundraiser_students").delete().eq(
        "fundraiser_id", fundraiser_id
    ).eq("user_id", user_id).execute()


def list_registered_students(fundraiser_id: str) -> list[dict]:
    # Explicit FK path required: fundraiser_students has two FKs to users
    # (user_id and added_by), so PostgREST needs the unambiguous hint.
    sb = get_supabase()
    return sb.table("fundraiser_students").select(
        "user_id, position, added_at, users!fundraiser_students_user_id_fkey(username, full_name)"
    ).eq("fundraiser_id", fundraiser_id).execute().data or []


# ── Committee members (free-text) ───────────────────────────────────────────
#
# Registro documental de membros do comitê do fundraiser em texto livre.
# NÃO concede login nem permissão — é só uma lista de nomes para a proposta.
# Quem tem permissão real de editar/submeter continua sendo controlado por
# fundraiser_students (que exige user_id real).


def list_committee_members(fundraiser_id: str) -> list[dict]:
    """Retorna todos os membros do comitê do fundraiser, em ordem de criação."""
    sb = get_supabase()
    return sb.table("fundraiser_committee_members").select(
        "id, member_name, position, created_at"
    ).eq("fundraiser_id", fundraiser_id).order("created_at").execute().data or []


def add_committee_member(fundraiser_id: str, *,
                         member_name: str,
                         position: str,
                         created_by_id: str | None = None) -> dict:
    """Adiciona um membro ao comitê. Nome é obrigatório; posição pode ser vazia."""
    if not member_name or not member_name.strip():
        raise ValidationError("Member name is required.")
    payload: dict[str, Any] = {
        "fundraiser_id": fundraiser_id,
        "member_name": member_name.strip(),
        "position": (position or "").strip(),
    }
    if created_by_id:
        payload["created_by_id"] = created_by_id
    sb = get_supabase()
    res = sb.table("fundraiser_committee_members").insert(payload).execute()
    return res.data[0] if res.data else {}


def delete_committee_member(member_id: str) -> None:
    """Remove um membro do comitê pelo id da linha."""
    sb = get_supabase()
    sb.table("fundraiser_committee_members").delete().eq("id", member_id).execute()


def update_committee_member(member_id: str, *,
                            member_name: str,
                            position: str) -> dict:
    """Atualiza nome e/ou posição de um membro existente."""
    if not member_name or not member_name.strip():
        raise ValidationError("Member name is required.")
    payload = {
        "member_name": member_name.strip(),
        "position": (position or "").strip(),
    }
    sb = get_supabase()
    res = sb.table("fundraiser_committee_members").update(payload).eq(
        "id", member_id
    ).execute()
    return res.data[0] if res.data else {}


# ── Closure checklists (quatro signatários) ─────────────────────────────────
#
# Este bloco substitui o antigo par update_rf_checklist / rf_checklist_complete
# por um mecanismo genérico que serve os 4 signatários: RF, DOF, Finance,
# Master. Os nomes antigos continuam existindo como wrappers finos no final
# do bloco, para não quebrar o código que ainda os chama.

_CHECKLIST_DEFS: dict[str, tuple[dict[str, str], str]] = {
    # signer_key : (items_dict, db_column_name)
    "rf":      (RF_CHECKLIST_ITEMS,      "rf_checklist"),
    "dof":     (DOF_CHECKLIST_ITEMS,     "dof_checklist"),
    "finance": (FINANCE_CHECKLIST_ITEMS, "finance_checklist"),
    "master":  (MASTER_CHECKLIST_ITEMS,  "master_checklist"),
}

# Em qual status cada signatário pode editar seu checklist. Fora desse
# status, as escritas são rejeitadas e a UI deve mostrar read-only.
_CHECKLIST_EDIT_STATUS: dict[str, str] = {
    "dof":     "reporting",        # DOF agora é o PRIMEIRO signatário do closure
    "rf":      "rf_confirming",    # RF é o SEGUNDO (antes era o primeiro)
    "finance": "finance_confirming",
    "master":  "master_confirming",
}


def get_checklist_items(signer: str) -> dict[str, str]:
    """Retorna os textos dos itens de checklist de um signatário."""
    if signer not in _CHECKLIST_DEFS:
        raise ValidationError(f"Signatário desconhecido: {signer}")
    return _CHECKLIST_DEFS[signer][0]


def update_checklist(fundraiser_id: str, signer: str,
                     checklist: dict[str, bool]) -> dict:
    """Persiste o checklist de um signatário.

    Aplica a regra de locking: um signatário só pode editar seu próprio
    checklist enquanto o fundraiser estiver no status correspondente.
    """
    if signer not in _CHECKLIST_DEFS:
        raise ValidationError(f"Signatário desconhecido: {signer}")
    items, column = _CHECKLIST_DEFS[signer]
    expected_status = _CHECKLIST_EDIT_STATUS[signer]

    fr = get_fundraiser(fundraiser_id)
    if not fr:
        raise ValidationError("Fundraiser não encontrado.")
    if fr["status"] != expected_status:
        raise ValidationError(
            f"Checklist de {signer.upper()} está bloqueado: o fundraiser "
            f"está em status '{STATUS_DISPLAY.get(fr['status'], fr['status'])}', "
            f"não '{STATUS_DISPLAY.get(expected_status, expected_status)}'."
        )

    # Só mantém chaves que existem no dict de itens; força booleanos.
    clean = {k: bool(checklist.get(k, False)) for k in items}
    return update_fundraiser_fields(fundraiser_id, {column: clean})


def checklist_complete(fr: dict, signer: str) -> bool:
    if signer not in _CHECKLIST_DEFS:
        return False
    items, column = _CHECKLIST_DEFS[signer]
    stored = fr.get(column) or {}
    return all(stored.get(k, False) for k in items)


def validate_for_closure_submission(fr: dict, signer: str) -> list[str]:
    """Retorna motivos legíveis pelos quais o signatário ainda não pode
    submeter o passo de closure. Lista vazia = pode prosseguir."""
    errors: list[str] = []
    expected_status = _CHECKLIST_EDIT_STATUS.get(signer)
    if fr.get("status") != expected_status:
        errors.append(
            f"Fundraiser precisa estar em status "
            f"'{STATUS_DISPLAY.get(expected_status, expected_status)}' "
            f"para {signer.upper()} submeter."
        )
    if not checklist_complete(fr, signer):
        items, column = _CHECKLIST_DEFS[signer]
        stored = fr.get(column) or {}
        missing = [items[k] for k in items if not stored.get(k, False)]
        errors.extend(f"Não marcado: {m}" for m in missing)
    return errors


# Wrappers de compatibilidade — NÃO apagar, código antigo da UI ainda usa.
def update_rf_checklist(fundraiser_id: str, checklist: dict[str, bool]) -> dict:
    return update_checklist(fundraiser_id, "rf", checklist)


def rf_checklist_complete(fr: dict) -> bool:
    return checklist_complete(fr, "rf")
