"""
Fundraiser service layer.

Pure Python business logic: CRUD on fundraisers and their children, financial
calculations (cost/revenue/profit/margin), stock reconciliation, and state
transitions. No Streamlit imports — this module must remain UI-agnostic so it
can be tested or reused from other entry points (CLI, API, tests).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from services.supabase_client import get_supabase


VALID_STATUSES = [
    "draft", "rf_review", "approved", "executing",
    "reporting", "closed", "rejected",
]

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft":      {"rf_review"},
    "rf_review":  {"approved", "rejected", "draft"},
    "approved":   {"executing"},
    "executing":  {"reporting"},
    "reporting":  {"closed", "rejected"},
    "closed":     set(),
    "rejected":   {"draft"},
}


class FundraiserError(Exception):
    pass


class InvalidTransition(FundraiserError):
    pass


class ValidationError(FundraiserError):
    pass


def check_transition(current: str, new: str) -> None:
    if new not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransition(
            f"Cannot transition fundraiser from '{current}' to '{new}'."
        )


@dataclass
class FinancialSummary:
    total_cost: Decimal = Decimal("0")
    max_possible_revenue: Decimal = Decimal("0")
    actual_revenue: Decimal = Decimal("0")
    actual_profit: Decimal = Decimal("0")
    profit_after_gst: Decimal = Decimal("0")
    overall_margin: Decimal = Decimal("0")
    target_profit: Decimal = Decimal("0")

    def as_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.__dict__.items()}


@dataclass
class StockRow:
    item_code: str
    purchased: int = 0
    sold: int = 0

    @property
    def unsold(self) -> int:
        return self.purchased - self.sold

    @property
    def over_sold(self) -> bool:
        return self.sold > self.purchased


def _settings() -> dict[str, Any]:
    sb = get_supabase()
    rows = sb.table("app_settings").select("key,value").execute().data or []
    return {r["key"]: r["value"] for r in rows}


def get_gst_rate() -> Decimal:
    return Decimal(str(_settings().get("gst_rate", 0.09)))


def get_min_margin() -> Decimal:
    return Decimal(str(_settings().get("min_profit_margin", 0.30)))


def get_quote_threshold() -> Decimal:
    return Decimal(str(_settings().get("quote_threshold", 1000)))


def get_currency() -> str:
    return _settings().get("currency", "SGD")


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


def update_fundraiser_fields(fundraiser_id: str, fields: dict) -> dict:
    allowed = {
        "name", "objective", "rf_in_charge_id", "committee_chair_id",
        "marketing_start", "marketing_end", "ordering_start", "ordering_end",
        "supplier_order_date", "delivery_date", "flyer_removal_date",
        "flyer_remover_name", "report_submission_deadline", "marketing_plan",
        "proposal_extra", "report_extra",
    }
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return get_fundraiser(fundraiser_id) or {}
    sb = get_supabase()
    res = sb.table("fundraisers").update(clean).eq("id", fundraiser_id).execute()
    return res.data[0] if res.data else {}


def transition_status(fundraiser_id: str, new_status: str) -> dict:
    fr = get_fundraiser(fundraiser_id)
    if not fr:
        raise ValidationError("Fundraiser not found.")
    check_transition(fr["status"], new_status)
    sb = get_supabase()
    res = sb.table("fundraisers").update({"status": new_status}).eq("id", fundraiser_id).execute()
    return res.data[0]


def list_items(fundraiser_id: str) -> list[dict]:
    sb = get_supabase()
    return sb.table("fundraiser_items").select("*").eq(
        "fundraiser_id", fundraiser_id
    ).order("item_code").execute().data or []


def upsert_item(fundraiser_id: str, item_code: str, *,
                item_name: str | None = None, supplier: str | None = None,
                quantity: int = 0, unit_cost: float = 0.0,
                notes: str | None = None) -> dict:
    if not item_code.strip():
        raise ValidationError("Item code is required.")
    if quantity < 0:
        raise ValidationError("Quantity must be non-negative.")
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
    sb = get_supabase()
    sb.table("fundraiser_items").delete().eq("id", item_id).execute()


def list_selling_options(fundraiser_id: str) -> list[dict]:
    sb = get_supabase()
    return sb.table("fundraiser_selling_options").select("*").eq(
        "fundraiser_id", fundraiser_id
    ).order("option_type").order("option_name").execute().data or []


def _compute_option_unit_cost(composition: dict[str, int],
                              items: list[dict]) -> Decimal:
    by_code = {it["item_code"]: Decimal(str(it["unit_cost"])) for it in items}
    total = Decimal("0")
    for code, qty in composition.items():
        if code not in by_code:
            raise ValidationError(f"Unknown item code in bundle composition: {code}")
        total += by_code[code] * Decimal(str(qty))
    return total


def upsert_selling_option(fundraiser_id: str, option_name: str, *,
                          option_type: str, composition: dict[str, int],
                          selling_price: float) -> dict:
    if option_type not in ("single", "bundle"):
        raise ValidationError("option_type must be 'single' or 'bundle'.")
    if not composition:
        raise ValidationError("Composition cannot be empty.")
    if any(int(v) < 1 for v in composition.values()):
        raise ValidationError("All composition quantities must be >= 1.")
    if option_type == "single" and len(composition) != 1:
        raise ValidationError("A 'single' option must contain exactly one item code.")
    items = list_items(fundraiser_id)
    unit_cost = _compute_option_unit_cost(composition, items)
    sb = get_supabase()
    min_margin = get_min_margin()
    price_dec = Decimal(str(selling_price))
    computed_margin = (
        (price_dec - unit_cost) / price_dec if price_dec > 0 else Decimal("0")
    )
    payload = {
        "fundraiser_id": fundraiser_id,
        "option_name": option_name.strip(),
        "option_type": option_type,
        "composition": composition,
        "unit_cost": float(unit_cost),
        "selling_price": float(selling_price),
        "is_acceptable": bool(computed_margin >= min_margin),
    }
    res = sb.table("fundraiser_selling_options").upsert(
        payload, on_conflict="fundraiser_id,option_name"
    ).execute()
    return res.data[0]


def delete_selling_option(option_id: str) -> None:
    sb = get_supabase()
    sb.table("fundraiser_selling_options").delete().eq("id", option_id).execute()


def bundle_implicit_discount(option: dict,
                             singles_by_code: dict[str, dict]) -> Decimal | None:
    if option["option_type"] != "bundle":
        return None
    composition = option["composition"] or {}
    total_single = Decimal("0")
    for code, qty in composition.items():
        s = singles_by_code.get(code)
        if not s:
            return None
        total_single += Decimal(str(s["selling_price"])) * Decimal(str(qty))
    return total_single - Decimal(str(option["selling_price"]))


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
    items = list_items(fundraiser_id)
    options = {o["id"]: o for o in list_selling_options(fundraiser_id)}
    movements = list_stock_movements(fundraiser_id)
    rows: dict[str, StockRow] = {
        it["item_code"]: StockRow(item_code=it["item_code"],
                                  purchased=int(it["quantity"]))
        for it in items
    }
    for mv in movements:
        opt = options.get(mv["selling_option_id"])
        if not opt:
            continue
        composition = opt["composition"] or {}
        qty_sold = int(mv["quantity_sold"])
        for code, qty_in_option in composition.items():
            if code not in rows:
                rows[code] = StockRow(item_code=code, purchased=0)
            rows[code].sold += qty_sold * int(qty_in_option)
    return sorted(rows.values(), key=lambda r: r.item_code)


def compute_financial_summary(fundraiser_id: str) -> FinancialSummary:
    items = list_items(fundraiser_id)
    options = list_selling_options(fundraiser_id)
    movements = {m["selling_option_id"]: int(m["quantity_sold"])
                 for m in list_stock_movements(fundraiser_id)}
    total_cost = sum(
        (Decimal(str(it["unit_cost"])) * Decimal(str(it["quantity"]))
         for it in items),
        Decimal("0"),
    )
    purchased_by_code = {it["item_code"]: int(it["quantity"]) for it in items}
    max_rev = Decimal("0")
    for opt in options:
        price = Decimal(str(opt["selling_price"]))
        comp = opt["composition"] or {}
        if not comp:
            continue
        try:
            max_units = min(
                purchased_by_code.get(code, 0) // int(qty)
                for code, qty in comp.items() if int(qty) > 0
            )
        except ValueError:
            max_units = 0
        max_rev += price * Decimal(max_units)
    actual_rev = sum(
        (Decimal(str(o["selling_price"])) * Decimal(movements.get(o["id"], 0))
         for o in options),
        Decimal("0"),
    )
    actual_profit = actual_rev - total_cost
    gst = get_gst_rate()
    profit_after_gst = actual_profit * (Decimal("1") - gst)
    overall_margin = (actual_profit / actual_rev) if actual_rev > 0 else Decimal("0")
    target_profit = total_cost * get_min_margin()
    return FinancialSummary(
        total_cost=total_cost,
        max_possible_revenue=max_rev,
        actual_revenue=actual_rev,
        actual_profit=actual_profit,
        profit_after_gst=profit_after_gst,
        overall_margin=overall_margin,
        target_profit=target_profit,
    )


def register_student(fundraiser_id: str, user_id: str, *,
                     position: str = "member") -> None:
    sb = get_supabase()
    sb.table("fundraiser_students").upsert(
        {"fundraiser_id": fundraiser_id, "user_id": user_id, "position": position},
        on_conflict="fundraiser_id,user_id",
    ).execute()


def unregister_student(fundraiser_id: str, user_id: str) -> None:
    sb = get_supabase()
    sb.table("fundraiser_students").delete().eq(
        "fundraiser_id", fundraiser_id
    ).eq("user_id", user_id).execute()


def list_registered_students(fundraiser_id: str) -> list[dict]:
    sb = get_supabase()
    return sb.table("fundraiser_students").select(
        "user_id, position, added_at, users(username, full_name)"
    ).eq("fundraiser_id", fundraiser_id).execute().data or []
