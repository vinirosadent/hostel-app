"""
Fundraiser detail — dynamic tabs, full workflow, gallery appendix, RF closure.

Tab layout (varies by status):
  Always:
    1. Proposal (description, dates, compliance)
    2. Committee
    3. Items to Purchase
    4. Selling Options  ← also houses Submit-to-RF for students (spec G)
    5. Appendix Marketing
    6. Appendix Artwork
  After Master approval (executing / reporting / closure):
    7. Stock Movement
  Reporting / closure stages:
    8. Report Confirmations
  Staff only (any stage):
    9. Purchaser List

Permission model:
  Student (creator or committee member) — edit while draft/rejected; read-only after.
  RF (in charge)     — edit while rf_review; approve / return.
  Master             — edit / approve at any stage.
  DOF (rlt_lead)     — confirm at dof_confirming.
  Finance (rlt_finan)— confirm at finance_confirming.
"""
from __future__ import annotations

import string
from datetime import date, datetime, timedelta
from typing import Optional

import streamlit as st

from components.ui import inject_theme, brand_stripe, status_badge, workflow_progress_bar, corporate_table
from components.auth_ui import render_sidebar_user
from services.auth_service import (
    require_login, is_staff, is_master, has_role, has_any_role,
)
from services.fundraiser_service import (
    STATUS_DISPLAY, RF_CHECKLIST_ITEMS,
    InvalidTransition, ValidationError, FundraiserError,
    get_fundraiser, update_fundraiser_fields,
    transition_status, validate_for_submission,
    list_items, upsert_item, delete_item,
    list_selling_options, upsert_selling_option, delete_selling_option,
    list_stock_movements, upsert_stock_movement,
    compute_stock_reconciliation, compute_financial_summary,
    list_assets, create_asset, update_asset_metadata, delete_asset,
    list_registered_students, register_student, unregister_student,
    update_rf_checklist, rf_checklist_complete,
    get_gst_rate,
)

def _parse_date(val: object) -> Optional[date]:
    """Convert Supabase date string or None to datetime.date for st.date_input."""
    if not val:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except (ValueError, TypeError):
        return None


def _reset_and_scroll(form_keys: list[str], success_msg: str) -> None:
    for k in form_keys:
        if k in st.session_state:
            del st.session_state[k]
    st.session_state["sh_action_msg"] = ("success", success_msg)
    st.markdown(
        "<script>window.parent.document.querySelector('section.main').scrollTo(0,0);</script>",
        unsafe_allow_html=True,
    )
    st.rerun()


st.set_page_config(
    page_title="Fundraiser — Sheares Hall Ops",
    page_icon="💰",
    layout="wide",
)
inject_theme()

user = require_login()
render_sidebar_user()

GST_RATE = float(get_gst_rate())


# ── Resolve fundraiser ─────────────────────────────────────────────────────

fr_id: str | None = st.session_state.get("sh_selected_fundraiser")
if not fr_id:
    st.info("No fundraiser selected. Open one from the Fundraisers list.")
    if st.button("← Back to Fundraisers"):
        st.switch_page("pages/10_Fundraisers.py")
    st.stop()

fr = get_fundraiser(fr_id)
if not fr:
    st.error("Fundraiser not found or you do not have access.")
    if st.button("← Back"):
        st.switch_page("pages/10_Fundraisers.py")
    st.stop()


def _reload() -> None:
    global fr
    fr = get_fundraiser(fr_id) or fr


# ── Derived permissions ────────────────────────────────────────────────────

status = fr["status"]
is_creator = fr.get("created_by_id") == user["id"]
is_rf_in_charge = fr.get("rf_in_charge_id") == user["id"]
_is_rf = has_role("resident_fellow")
_is_master = is_master()
_is_dof = has_any_role(["rlt_lead", "master"])
_is_finance = has_any_role(["rlt_finan", "master"])

# Load committee roster at top level — query is now safe after Phase 1 FK fix
_students_raw: list[dict] = []
try:
    _students_raw = list_registered_students(fr_id)
except Exception:
    _students_raw = []

is_committee_member = any(s["user_id"] == user["id"] for s in _students_raw)

# Draft: creator OR any committee member can edit; RF is hands-on from draft; Master always
can_edit_proposal = (
    ((is_creator or is_committee_member) and status in ("draft", "rejected"))
    or (_is_rf and is_rf_in_charge and status in ("draft", "rejected", "rf_review"))
    or (is_staff() and not _is_rf and status in ("rf_review", "master_review"))
    or _is_master
)
can_edit_report = (
    is_staff()
    or (is_creator and status in ("executing", "reporting"))
)
can_edit_appendix = (
    can_edit_proposal
    or (is_staff() and status in ("rf_review", "master_review"))
)


# ── Post-action banner ─────────────────────────────────────────────────────

if st.session_state.get("sh_action_msg"):
    msg_type, msg_text = st.session_state.pop("sh_action_msg")
    if msg_type == "success":
        st.success(msg_text)
    else:
        st.info(msg_text)


# ── Header ─────────────────────────────────────────────────────────────────

col_hd, col_st = st.columns([4, 1])
with col_hd:
    st.markdown(f"# {fr['name']}")
with col_st:
    st.markdown(status_badge(status), unsafe_allow_html=True)
    st.caption(STATUS_DISPLAY.get(status, status.replace("_", " ").title()))

brand_stripe()


# ── Progress bar ───────────────────────────────────────────────────────────

def _fmt_date(val: object) -> str:
    if not val:
        return ""
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%y")
    except Exception:
        return ""


_STATUS_RANK = [
    "draft", "rejected", "rf_review", "master_review",
    "approved", "executing", "reporting",
    "dof_confirming", "finance_confirming", "master_confirming", "closed",
]

# Timeline stage definitions — labels refined per spec H ("The Master", no ALL-CAPS)
_APPROVAL_STAGES = [
    {
        "label": "Drafting",
        "rank": 0,
        "statuses": {"draft", "rejected"},
        "ts": "created_at",
    },
    {
        "label": "Submitted to RF",
        "rank": 2,
        "statuses": {"rf_review"},
        "ts": "submitted_at",
    },
    {
        "label": "Approved by RF",
        "rank": 3,
        "statuses": {"master_review"},
        "ts": "rf_approved_at",
    },
    {
        "label": "Approved by The Master",
        "rank": 4,
        "statuses": {"approved", "executing", "reporting",
                      "dof_confirming", "finance_confirming",
                      "master_confirming", "closed"},
        "ts": "master_approved_at",
    },
]


def _cur_rank() -> int:
    try:
        return _STATUS_RANK.index(status)
    except ValueError:
        return 0


def _build_progress_stages() -> list[dict]:
    cur = _cur_rank()
    stages = []
    for i, sdef in enumerate(_APPROVAL_STAGES):
        date_str = _fmt_date(fr.get(sdef["ts"])) if fr.get(sdef["ts"]) else ""

        if status == "rejected" and i == 0:
            state = "rejected"
        elif cur > sdef["rank"]:
            state = "completed"
        elif cur == sdef["rank"] or status in sdef["statuses"]:
            state = "current"
        else:
            state = "pending"
            date_str = ""  # pending stages never have a date

        stages.append({"label": sdef["label"], "state": state, "date_str": date_str})
    return stages


st.markdown(workflow_progress_bar(_build_progress_stages()), unsafe_allow_html=True)


# ── Dynamic tab construction (spec F) ──────────────────────────────────────
# Stock Movement: only after Master approval (approved / executing / reporting / closure)
# Report Confirmations: only during reporting / closure stages
# Purchaser List: staff only

_show_stock = status not in ("draft", "rejected", "rf_review", "master_review")
_show_report = status in (
    "reporting", "dof_confirming", "finance_confirming", "master_confirming", "closed"
)
_show_purchaser = is_staff()

_tab_labels: list[str] = [
    "📋 Proposal",
    "👥 Committee",
    "📦 Items",
    "💰 Selling Options",
    "📢 Appendix Marketing",
    "🎨 Appendix Artwork",
]
if _show_stock:
    _tab_labels.append("📊 Stock Movement")
if _show_report:
    _tab_labels.append("✅ Report Confirmations")
if _show_purchaser:
    _tab_labels.append("📋 Purchaser List")

_all_tabs = st.tabs(_tab_labels)
_ti = 0

tab_proposal  = _all_tabs[_ti]; _ti += 1
tab_committee = _all_tabs[_ti]; _ti += 1
tab_items     = _all_tabs[_ti]; _ti += 1
tab_selling   = _all_tabs[_ti]; _ti += 1
tab_mkt       = _all_tabs[_ti]; _ti += 1
tab_art       = _all_tabs[_ti]; _ti += 1

tab_stock     = _all_tabs[_ti] if _show_stock    else None
if _show_stock:    _ti += 1
tab_report    = _all_tabs[_ti] if _show_report   else None
if _show_report:   _ti += 1
tab_purchaser = _all_tabs[_ti] if _show_purchaser else None


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PROPOSAL DESCRIPTION
# ══════════════════════════════════════════════════════════════════════════════

with tab_proposal:
    col_l, col_r = st.columns([1, 1])
    with col_l:
        t1_name = st.text_input(
            "Name of Project *",
            value=fr.get("name") or "",
            disabled=not can_edit_proposal,
            key="t1_name",
        )
        t1_desc = st.text_area(
            "Project Description *",
            value=fr.get("objective") or "",
            height=120,
            disabled=not can_edit_proposal,
            key="t1_desc",
            help="Describe the purpose, goals, and what the fundraiser is for.",
        )
        t1_beneficiary = st.text_input(
            "Beneficiary",
            value=fr.get("beneficiary") or "",
            disabled=not can_edit_proposal,
            key="t1_beneficiary",
            placeholder="e.g. Sheares Hall Sports Fund, Charity XYZ",
        )
        t1_prepared_by = st.text_input(
            "Proposal prepared by *",
            value=fr.get("proposal_prepared_by") or (
                user["full_name"] if status in ("draft", "rejected") else ""
            ),
            disabled=not can_edit_proposal,
            key="t1_prepared_by",
            help="Full name of the student drafting this proposal.",
        )
        t1_on_behalf_of = st.text_input(
            "On behalf of Committee / Activity *",
            value=fr.get("on_behalf_of") or "",
            disabled=not can_edit_proposal,
            key="t1_on_behalf_of",
            placeholder="e.g. Block A Welfare Committee, Christmas Drive 2025",
            help="Name of the committee or activity this fundraiser supports.",
        )
        t1_flyer_person = st.text_input(
            "Person responsible for flyer removal",
            value=fr.get("flyer_remover_name") or "",
            disabled=not can_edit_proposal,
            key="t1_flyer_person",
        )

    with col_r:
        st.markdown("#### Timeline")
        t1_mkt_start = st.date_input(
            "Marketing Start Date",
            value=_parse_date(fr.get("marketing_start")),
            disabled=not can_edit_proposal,
            key="t1_mkt_start",
        )
        t1_mkt_end = st.date_input(
            "Marketing End Date",
            value=_parse_date(fr.get("marketing_end")),
            disabled=not can_edit_proposal,
            key="t1_mkt_end",
        )
        t1_ord_start = st.date_input(
            "Ordering Start Date",
            value=_parse_date(fr.get("ordering_start")),
            disabled=not can_edit_proposal,
            key="t1_ord_start",
        )
        t1_ord_end = st.date_input(
            "Ordering End Date",
            value=_parse_date(fr.get("ordering_end")),
            disabled=not can_edit_proposal,
            key="t1_ord_end",
        )
        t1_supplier_date = st.date_input(
            "Date of Ordering from Supplier",
            value=_parse_date(fr.get("supplier_order_date")),
            disabled=not can_edit_proposal,
            key="t1_supplier_date",
        )
        t1_delivery = st.date_input(
            "Expected Delivery / Fundraiser Closing Date *",
            value=_parse_date(fr.get("delivery_date")),
            disabled=not can_edit_proposal,
            key="t1_delivery",
            help="Used to auto-calculate the flyer removal and report deadlines.",
        )

        if t1_delivery:
            flyer_date = t1_delivery + timedelta(days=7)
            report_date = t1_delivery + timedelta(days=21)
            st.markdown(
                f"<div style='background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;"
                f"padding:0.6rem 1rem;margin-top:0.5rem;font-size:0.88rem;'>"
                f"📌 <b>Flyers must be removed by:</b> {flyer_date.strftime('%d/%m/%Y')}<br>"
                f"📅 <b>Report must be submitted by:</b> {report_date.strftime('%d/%m/%Y')}"
                f"</div>",
                unsafe_allow_html=True,
            )
            flyer_date_str = str(flyer_date)
            report_date_str = str(report_date)
        else:
            flyer_date_str = None
            report_date_str = None

    st.markdown("---")

    st.markdown("#### Mandatory Compliance Confirmation")
    st.caption(
        "All four declarations must be confirmed before this proposal can be submitted to the RF. "
        "Saving a draft does not require them to be checked."
    )

    _compliance_items = [
        ("compliance_nusync",
         "All funds will be collected exclusively through **NUSync**. "
         "No other payment channels will be used."),
        ("compliance_no_intermediary",
         "Students will not act as intermediaries by receiving funds in personal accounts "
         "and then transferring money to the Office."),
        ("compliance_gst_artwork",
         "All marketing artwork will include the statement: **\"Prices inclusive of GST\"**."),
        ("compliance_regulations",
         "All committee members acknowledge compliance with NUS regulations and understand that "
         "mismanagement of funds or items may result in **disciplinary action**."),
    ]

    compliance_values: dict[str, bool] = {}
    for key, label in _compliance_items:
        compliance_values[key] = st.checkbox(
            label,
            value=bool(fr.get(key, False)),
            disabled=not can_edit_proposal,
            key=f"t1_{key}",
        )

    all_compliance_ok = all(compliance_values.values())
    if can_edit_proposal and not all_compliance_ok:
        st.info("ℹ️ All compliance boxes must be checked before you can submit to RF.")

    st.markdown("---")

    if can_edit_proposal:
        if st.button("💾 Save Draft", type="primary", key="t1_save"):
            if not t1_name.strip():
                st.error("Project name is required.")
            else:
                try:
                    update_fundraiser_fields(fr_id, {
                        "name": t1_name.strip(),
                        "objective": t1_desc.strip() or None,
                        "beneficiary": t1_beneficiary.strip() or None,
                        "proposal_prepared_by": t1_prepared_by.strip() or None,
                        "on_behalf_of": t1_on_behalf_of.strip() or None,
                        "marketing_start": str(t1_mkt_start) if t1_mkt_start else None,
                        "marketing_end": str(t1_mkt_end) if t1_mkt_end else None,
                        "ordering_start": str(t1_ord_start) if t1_ord_start else None,
                        "ordering_end": str(t1_ord_end) if t1_ord_end else None,
                        "supplier_order_date": str(t1_supplier_date) if t1_supplier_date else None,
                        "delivery_date": str(t1_delivery) if t1_delivery else None,
                        "flyer_removal_date": flyer_date_str,
                        "flyer_remover_name": t1_flyer_person.strip() or None,
                        "report_submission_deadline": report_date_str,
                        **compliance_values,
                    })
                    st.success("Draft saved.")
                    _reload()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Save failed: {exc}")
    else:
        # Show a neutral read-only notice; never say "locked" for a draft
        _status_label = STATUS_DISPLAY.get(status, status.replace("_", " ").title())
        if status in ("draft", "rejected"):
            st.caption(
                "You are viewing this proposal in read-only mode. "
                "Committee members and the creator can edit draft proposals."
            )
        else:
            st.caption(f"This proposal is read-only at its current stage: {_status_label}.")

    # Signatures (read-only display)
    _sigs = [
        ("Submitted by",           fr.get("submitted_by_name"),  fr.get("submitted_at")),
        ("Approved by RF",         fr.get("rf_approved_by"),     fr.get("rf_approved_at")),
        ("Approved by The Master", fr.get("master_approved_by"), fr.get("master_approved_at")),
    ]
    visible_sigs = [(l, n, d) for l, n, d in _sigs if n]
    if visible_sigs:
        st.markdown("---")
        st.markdown("#### Proposal Signatures")
        for label, name, dt in visible_sigs:
            st.markdown(
                f"<div class='sh-sig-block'>"
                f"<div><div class='sh-sig-label'>{label}</div>"
                f"<div class='sh-sig-name'>{name}</div></div>"
                f"<div class='sh-sig-date'>{_fmt_date(dt)}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — COMMITTEE
# ══════════════════════════════════════════════════════════════════════════════

with tab_committee:
    st.markdown("#### Committee Members")
    # Reuse pre-loaded roster — avoids redundant query
    students = _students_raw
    if not students:
        st.info("No committee members registered yet.")
    else:
        for s in students:
            udata = s.get("users") or {}
            full_name = udata.get("full_name") or udata.get("username") or s.get("user_id", "?")
            pos = (s.get("position") or "member").replace("_", " ").title()
            col_nm, col_pos, col_del = st.columns([4, 2, 1])
            with col_nm:
                st.markdown(f"**{full_name}**")
            with col_pos:
                st.caption(pos)
            with col_del:
                if can_edit_proposal and st.button(
                    "Remove", key=f"rm_student_{s['user_id']}"
                ):
                    unregister_student(fr_id, s["user_id"])
                    st.rerun()

    if can_edit_proposal:
        st.markdown("---")
        st.markdown("#### Add Member")
        from services.supabase_client import get_supabase as _gsb
        all_users = _gsb().table("users").select(
            "id, full_name, username"
        ).eq("is_active", True).execute().data or []
        existing_ids = {s["user_id"] for s in students}
        eligible = [u for u in all_users if u["id"] not in existing_ids]
        if eligible:
            user_map = {f"{u['full_name']} ({u['username']})": u["id"] for u in eligible}
            sel_label = st.selectbox("Select user", list(user_map.keys()), key="add_member_sel")
            pos_opts = ["chair", "vice_chair", "treasurer", "secretary", "member"]
            sel_pos = st.selectbox("Position", pos_opts, key="add_member_pos")
            if st.button("➕ Add to committee", type="primary", key="add_member_btn"):
                register_student(
                    fr_id, user_map[sel_label],
                    position=sel_pos, added_by_id=user["id"]
                )
                st.success("Member added.")
                st.rerun()
        else:
            st.caption("All active users are already members.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — ITEMS TO PURCHASE
# ══════════════════════════════════════════════════════════════════════════════

with tab_items:
    items = list_items(fr_id)

    def _next_code(existing: list[dict]) -> str:
        taken = {it["item_code"] for it in existing}
        for c in string.ascii_uppercase:
            if c not in taken:
                return c
        for c1 in string.ascii_uppercase:
            for c2 in string.ascii_uppercase:
                if c1 + c2 not in taken:
                    return c1 + c2
        return "X"

    # ── Inline edit form (shown above table when editing) ─────────────────
    _edit_item_id = st.session_state.get("sh_edit_item_id")
    if _edit_item_id and can_edit_proposal:
        _edit_it = next((it for it in items if it["id"] == _edit_item_id), None)
        if _edit_it:
            _ename_d = _edit_it.get("item_name") or _edit_it["item_code"]
            _euc = float(_edit_it["unit_cost"])
            _eqty = int(_edit_it["quantity"])
            with st.container(border=True):
                st.markdown(f"**Edit Item — {_ename_d}**")
                ec1, ec2, ec3, ec4 = st.columns([3, 2, 2, 2])
                with ec1:
                    e_name = st.text_input("Item name", value=_ename_d,
                                           key=f"ename_{_edit_item_id}")
                with ec2:
                    e_supp = st.text_input("Supplier",
                                           value=_edit_it.get("supplier") or "",
                                           key=f"esupp_{_edit_item_id}")
                with ec3:
                    e_qty = st.number_input("Quantity", value=_eqty, min_value=1,
                                            key=f"eqty_{_edit_item_id}")
                with ec4:
                    e_cost = st.number_input("Unit Cost (SGD)", value=_euc,
                                              min_value=0.0, format="%.2f",
                                              key=f"ecost_{_edit_item_id}")
                e_total = e_cost * e_qty
                quote_note = "  ⚠️ *Quote required (total ≥ SGD 1,000)*" if e_total >= 1000 else ""
                st.info(f"Total Cost: **SGD {e_total:,.2f}**{quote_note}")
                cs, cc = st.columns(2)
                with cs:
                    if st.button("✅ Confirm", key=f"esave_{_edit_item_id}",
                                 type="primary", use_container_width=True):
                        if not e_name.strip():
                            st.error("Item name cannot be empty.")
                        else:
                            try:
                                upsert_item(
                                    fr_id, _edit_it["item_code"],
                                    item_name=e_name.strip(),
                                    supplier=e_supp.strip() or None,
                                    quantity=int(e_qty),
                                    unit_cost=float(e_cost),
                                )
                                _reset_and_scroll(
                                    [f"ename_{_edit_item_id}", f"esupp_{_edit_item_id}",
                                     f"eqty_{_edit_item_id}", f"ecost_{_edit_item_id}",
                                     "sh_edit_item_id"],
                                    f"Item '{e_name.strip()}' saved.",
                                )
                            except Exception as ex:
                                st.error(f"Save failed: {ex}")
                with cc:
                    if st.button("Cancel", key=f"ecancel_{_edit_item_id}",
                                 use_container_width=True):
                        st.session_state.pop("sh_edit_item_id", None)
                        st.rerun()

    # ── Corporate table ───────────────────────────────────────────────────
    _items_cols = [
        {"key": "item_code",    "label": "Code",            "flex": 1, "mono": True},
        {"key": "item_name",    "label": "Name",            "flex": 3},
        {"key": "supplier",     "label": "Supplier",        "flex": 2},
        {"key": "quantity",     "label": "Qty",             "flex": 1, "align": "right"},
        {"key": "unit_cost_f",  "label": "Unit Cost (SGD)", "flex": 2, "align": "right"},
        {"key": "total_f",      "label": "Total (SGD)",     "flex": 2, "align": "right"},
        {"key": "quote_f",      "label": "Quote?",          "flex": 1, "align": "center"},
    ]

    grand_total = 0.0
    _items_rows: list[dict] = []
    for it in items:
        uc = float(it["unit_cost"])
        qty = int(it["quantity"])
        tc = uc * qty
        grand_total += tc
        _items_rows.append({
            "id": it["id"],
            "item_code": it["item_code"],
            "item_name": it.get("item_name") or it["item_code"],
            "supplier": it.get("supplier") or "—",
            "quantity": qty,
            "unit_cost_f": f"{uc:,.2f}",
            "total_f": f"{tc:,.2f}",
            "quote_f": "⚠️ Yes" if it.get("requires_quote") else "No",
        })

    def _item_actions(row: dict) -> None:
        ca, cb = st.columns(2)
        with ca:
            if st.button("✏️", key=f"edit_item_{row['id']}",
                         use_container_width=True, help="Edit"):
                st.session_state["sh_edit_item_id"] = row["id"]
                st.rerun()
        with cb:
            if st.button("🗑️", key=f"del_item_btn_{row['id']}",
                         use_container_width=True, help="Delete"):
                st.session_state["sh_confirm_del_item"] = row["id"]
                st.rerun()

    corporate_table(
        _items_cols,
        _items_rows,
        empty_text="No items registered yet.",
        row_actions_fn=_item_actions if can_edit_proposal else None,
    )

    if _items_rows:
        st.markdown(
            f"<div style='text-align:right;font-weight:600;color:#0f172a;"
            f"padding:0.5rem 0;border-top:2px solid #e2e8f0;margin-top:0.25rem;'>"
            f"Total Cost of All Items: SGD {grand_total:,.2f}</div>",
            unsafe_allow_html=True,
        )

    # ── Delete confirmation ────────────────────────────────────────────────
    _del_item_id = st.session_state.get("sh_confirm_del_item")
    if _del_item_id:
        _del_it = next((it for it in items if it["id"] == _del_item_id), None)
        if _del_it:
            _del_name = _del_it.get("item_name") or _del_it["item_code"]
            with st.container(border=True):
                st.warning(f"Delete **{_del_name}**? This cannot be undone.")
                ca, cb = st.columns(2)
                with ca:
                    if st.button("Yes, delete", key=f"confirm_del_item_{_del_item_id}",
                                 type="primary"):
                        delete_item(_del_item_id)
                        st.session_state.pop("sh_confirm_del_item", None)
                        st.session_state.pop("sh_edit_item_id", None)
                        st.rerun()
                with cb:
                    if st.button("Cancel", key=f"cancel_del_item_{_del_item_id}"):
                        st.session_state.pop("sh_confirm_del_item", None)
                        st.rerun()

    if can_edit_proposal:
        st.markdown("---")
        if st.button(
            "➕ Add Item", key="toggle_add_item",
            type="secondary" if st.session_state.get("sh_adding_item") else "primary",
        ):
            st.session_state["sh_adding_item"] = not st.session_state.get("sh_adding_item", False)
            st.rerun()

        if st.session_state.get("sh_adding_item"):
            with st.container(border=True):
                st.markdown("**New Item**")
                ai1, ai2, ai3, ai4 = st.columns([3, 2, 2, 2])
                with ai1:
                    new_name = st.text_input("Item name *", key="add_item_name",
                                              placeholder="e.g. T-shirt, Shorts, Socks")
                with ai2:
                    new_supp = st.text_input("Supplier", key="add_item_supplier",
                                              placeholder="e.g. Sportswear Co.")
                with ai3:
                    new_qty = st.number_input("Quantity *", min_value=1, value=1,
                                               key="add_item_qty")
                with ai4:
                    new_cost = st.number_input("Unit Cost (SGD) *", min_value=0.0,
                                                value=0.0, format="%.2f",
                                                key="add_item_cost")

                calc = new_cost * new_qty
                if calc > 0:
                    note = "  ⚠️ *Supplier quote required (total ≥ SGD 1,000)*" if calc >= 1000 else ""
                    st.info(f"Total Cost: **SGD {calc:.2f}**{note}")

                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("✅ Confirm Add", type="primary", key="confirm_add_item"):
                        if not new_name.strip():
                            st.error("Item name is required.")
                        elif new_cost < 0:
                            st.error("Unit cost cannot be negative.")
                        else:
                            code = _next_code(items)
                            try:
                                upsert_item(
                                    fr_id, code,
                                    item_name=new_name.strip(),
                                    supplier=new_supp.strip() or None,
                                    quantity=int(new_qty),
                                    unit_cost=float(new_cost),
                                )
                                _reset_and_scroll(
                                    ["add_item_name", "add_item_supplier",
                                     "add_item_qty", "add_item_cost", "sh_adding_item"],
                                    f"Item '{new_name.strip()}' added.",
                                )
                            except Exception as ex:
                                st.error(f"Could not add item: {ex}")
                with cc2:
                    if st.button("Cancel", key="cancel_add_item"):
                        st.session_state.pop("sh_adding_item", None)
                        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — SELLING OPTIONS  (also houses Submit-to-RF per spec G)
# ══════════════════════════════════════════════════════════════════════════════

with tab_selling:
    items_for_selling = list_items(fr_id)
    item_map = {it["item_code"]: it for it in items_for_selling}
    item_display = {
        it["item_code"]: (it.get("item_name") or it["item_code"])
        for it in items_for_selling
    }

    st.info(
        "ℹ️ **Selling Price** shown here is **before GST**. "
        f"The **Final Customer Price (GST-inclusive)** = Selling Price × {1 + GST_RATE:.0%}. "
        "GST collected from customers is remitted to the government — it is not part of the Committee's profit."
    )

    # FIX 11 — singles first (alphabetical), bundles second (alphabetical)
    options = sorted(
        list_selling_options(fr_id),
        key=lambda x: (0 if x["option_type"] == "single" else 1, x["option_name"].lower()),
    )

    # ── Inline edit form (above table) ────────────────────────────────────
    _edit_opt_id = st.session_state.get("sh_edit_opt_id")
    if _edit_opt_id and can_edit_proposal:
        _edit_o = next((o for o in options if o["id"] == _edit_opt_id), None)
        if _edit_o:
            _euc = float(_edit_o["unit_cost"])
            _esp = float(_edit_o["selling_price"])
            _ecomp = _edit_o.get("composition") or {}
            with st.container(border=True):
                st.markdown(f"**Edit Option — {_edit_o['option_name']}**")
                eo1, eo2 = st.columns([3, 2])
                with eo1:
                    e_opt_name = st.text_input(
                        "Option name", value=_edit_o["option_name"],
                        key=f"eoptname_{_edit_opt_id}",
                    )
                with eo2:
                    e_opt_price = st.number_input(
                        "Selling Price before GST (SGD)", value=_esp,
                        min_value=0.0, format="%.2f", key=f"eoptprice_{_edit_opt_id}",
                    )
                if e_opt_price > 0:
                    ep = e_opt_price - _euc
                    ep_pct = (ep / _euc * 100) if _euc > 0 else 0
                    efinal = e_opt_price * (1 + GST_RATE)
                    col_col = "green" if ep_pct >= 20 else "red"
                    st.markdown(
                        f"Unit Cost: **SGD {_euc:,.2f}** · "
                        f"Selling Price (ex-GST): **SGD {e_opt_price:,.2f}** · "
                        f"Final Price: **SGD {efinal:,.2f}**<br>"
                        f"<span style='color:{col_col}'>Profit: **SGD {ep:,.2f}** "
                        f"({ep_pct:.1f}%)</span>",
                        unsafe_allow_html=True,
                    )
                es, ec_btn = st.columns(2)
                with es:
                    if st.button("✅ Confirm", key=f"saveopt_{_edit_opt_id}",
                                 type="primary", use_container_width=True):
                        if not e_opt_name.strip():
                            st.error("Option name cannot be empty.")
                        elif e_opt_price <= 0:
                            st.error("Selling price must be greater than zero.")
                        else:
                            try:
                                upsert_selling_option(
                                    fr_id, e_opt_name.strip(),
                                    option_type=_edit_o["option_type"],
                                    composition=_ecomp,
                                    selling_price=float(e_opt_price),
                                    option_id=_edit_o["id"],
                                )
                                _reset_and_scroll(
                                    [f"eoptname_{_edit_opt_id}",
                                     f"eoptprice_{_edit_opt_id}",
                                     "sh_edit_opt_id"],
                                    f"Option '{e_opt_name.strip()}' saved.",
                                )
                            except Exception as ex:
                                st.error(f"Save failed: {ex}")
                with ec_btn:
                    if st.button("Cancel", key=f"cancelopt_{_edit_opt_id}",
                                 use_container_width=True):
                        st.session_state.pop("sh_edit_opt_id", None)
                        st.rerun()

    # ── Corporate table ───────────────────────────────────────────────────
    _opts_cols = [
        {"key": "option_type_f",  "label": "Type",                      "flex": 1},
        {"key": "option_name",    "label": "Option",                     "flex": 3},
        {"key": "composition_str","label": "Composition",                "flex": 3},
        {"key": "unit_cost_f",    "label": "Unit Cost (SGD)",            "flex": 2, "align": "right"},
        {"key": "sell_f",         "label": "Sell ex-GST (SGD)",          "flex": 2, "align": "right"},
        {"key": "final_f",        "label": "Final Price inc. GST (SGD)", "flex": 2, "align": "right"},
        {"key": "profit_f",       "label": "Profit (SGD / %)",           "flex": 2, "align": "right"},
    ]

    _opts_rows: list[dict] = []
    for o in options:
        comp = o.get("composition") or {}
        comp_str = ", ".join(f"{item_display.get(k, k)} ×{v}" for k, v in comp.items())
        uc = float(o["unit_cost"])
        sp = float(o["selling_price"])
        profit = sp - uc
        profit_pct = (profit / uc * 100) if uc > 0 else 0.0
        final_price = sp * (1 + GST_RATE)
        ok = o.get("is_acceptable", False)
        p_cls = "sh-profit-ok" if ok else "sh-profit-bad"
        _opts_rows.append({
            "id": o["id"],
            "option_type":   o["option_type"],
            "option_type_f": o["option_type"].capitalize(),
            "option_name":   o["option_name"],
            "composition_str": comp_str or "—",
            "unit_cost_f": f"{uc:,.2f}",
            "sell_f":      f"{sp:,.2f}",
            "final_f":     f"{final_price:,.2f}",
            "profit_f":    f'<span class="{p_cls}">{profit:,.2f} ({profit_pct:.1f}%)</span>',
        })

    def _opt_actions(row: dict) -> None:
        ca, cb = st.columns(2)
        with ca:
            if st.button("✏️", key=f"editopt_{row['id']}",
                         use_container_width=True, help="Edit"):
                st.session_state["sh_edit_opt_id"] = row["id"]
                st.rerun()
        with cb:
            if st.button("🗑️", key=f"delopt_btn_{row['id']}",
                         use_container_width=True, help="Delete"):
                st.session_state["sh_confirm_del_opt"] = row["id"]
                st.rerun()

    corporate_table(
        _opts_cols,
        _opts_rows,
        empty_text="No selling options yet.",
        row_actions_fn=_opt_actions if can_edit_proposal else None,
    )

    if options and not all(o.get("is_acceptable") for o in options):
        st.warning("⚠️ One or more options are below the minimum profit target.")

    # ── Delete confirmation ────────────────────────────────────────────────
    _del_opt_id = st.session_state.get("sh_confirm_del_opt")
    if _del_opt_id:
        _del_o = next((o for o in options if o["id"] == _del_opt_id), None)
        if _del_o:
            with st.container(border=True):
                st.warning(f"Delete **{_del_o['option_name']}**? This cannot be undone.")
                da, db = st.columns(2)
                with da:
                    if st.button("Yes, delete", key=f"confirm_del_opt_{_del_opt_id}",
                                 type="primary"):
                        delete_selling_option(_del_opt_id)
                        st.session_state.pop("sh_confirm_del_opt", None)
                        st.rerun()
                with db:
                    if st.button("Cancel", key=f"cancel_del_opt_{_del_opt_id}"):
                        st.session_state.pop("sh_confirm_del_opt", None)
                        st.rerun()

    if options:
        st.markdown("---")
        st.markdown("#### Summary")
        items_for_summary = list_items(fr_id)
        total_cost_s = sum(
            float(it["unit_cost"]) * int(it["quantity"]) for it in items_for_summary
        )
        st.markdown(
            f"<div style='display:flex;gap:1.5rem;flex-wrap:wrap;margin-bottom:0.5rem;'>"
            f"<div><b>Total Cost (items purchased)</b><br>SGD {total_cost_s:,.2f}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Add new selling option form ────────────────────────────────────────
    if can_edit_proposal:
        if not items_for_selling:
            st.warning("Add items in the **Items** tab first before creating selling options.")
        else:
            st.markdown("---")
            opt_type = st.radio(
                "Add a new selling option",
                ["Single Item Sale", "Combo / Bundle"],
                horizontal=True,
                key="so_type_radio",
            )

            item_labels = [item_display[c] for c in item_display]
            item_codes = list(item_display.keys())

            with st.container(border=True):
                if opt_type == "Single Item Sale":
                    st.markdown("**Single Item Sale**")
                    sel_label = st.selectbox("Select item *", item_labels, key="so_single_item")
                    sel_code = item_codes[item_labels.index(sel_label)]
                    uc_single = float(item_map[sel_code]["unit_cost"])

                    st.markdown(f"Unit Cost (from purchase): **SGD {uc_single:.2f}**")
                    so_sell = st.number_input(
                        "Selling Price before GST (SGD) *", min_value=0.0, value=0.0,
                        format="%.2f", key="so_single_price",
                    )
                    if so_sell > 0:
                        p_s = so_sell - uc_single
                        p_pct_s = (p_s / uc_single * 100) if uc_single > 0 else 0
                        final_s = so_sell * (1 + GST_RATE)
                        col_s = "green" if p_pct_s >= 20 else "red"
                        st.markdown(
                            f"Final Customer Price (GST-incl.): **SGD {final_s:.2f}**<br>"
                            f"<span style='color:{col_s}'>Nominal Profit: **SGD {p_s:.2f}** "
                            f"({p_pct_s:.1f}%)</span>",
                            unsafe_allow_html=True,
                        )

                    auto_name_s = f"Single – {sel_label}"
                    so_name_s = st.text_input("Option name", value=auto_name_s,
                                               key="so_single_name")

                    c_add, c_cancel = st.columns([2, 1])
                    with c_add:
                        if st.button("✅ Confirm — Add Single Option", type="primary",
                                     key="so_single_submit"):
                            if so_sell <= 0:
                                st.error("Selling price must be greater than zero.")
                            else:
                                try:
                                    upsert_selling_option(
                                        fr_id, (so_name_s or auto_name_s).strip(),
                                        option_type="single",
                                        composition={sel_code: 1},
                                        selling_price=float(so_sell),
                                    )
                                    _reset_and_scroll(
                                        ["so_single_item", "so_single_price",
                                         "so_single_name", "so_type_radio"],
                                        f"Option '{(so_name_s or auto_name_s).strip()}' added.",
                                    )
                                except (ValidationError, Exception) as ex:
                                    st.error(f"Error: {ex}")

                else:
                    st.markdown("**Combo / Bundle**")
                    sel_labels_c = st.multiselect(
                        "Select items for combo (at least 2 different items) *",
                        item_labels,
                        key="so_combo_items",
                    )
                    composition_c: dict[str, int] = {}
                    combo_cost = 0.0

                    if sel_labels_c:
                        st.markdown("**Quantity of each item in the combo:**")
                        n_cols = min(4, len(sel_labels_c))
                        qty_cols = st.columns(n_cols)
                        for idx, lbl in enumerate(sel_labels_c):
                            code_c = item_codes[item_labels.index(lbl)]
                            with qty_cols[idx % n_cols]:
                                q_c = st.number_input(lbl, min_value=1, value=1,
                                                       key=f"so_combo_qty_{code_c}")
                            composition_c[code_c] = int(q_c)
                            combo_cost += float(item_map[code_c]["unit_cost"]) * int(q_c)

                        st.markdown(f"Combined Unit Cost: **SGD {combo_cost:.2f}**")

                    so_name_c = st.text_input(
                        "Combo name *", key="so_combo_name",
                        placeholder="e.g. Full Package, T-shirt + Shorts",
                    )
                    so_sell_c = st.number_input(
                        "Combo Selling Price before GST (SGD) *",
                        min_value=0.0, value=0.0, format="%.2f", key="so_combo_price",
                    )
                    if so_sell_c > 0 and combo_cost > 0:
                        p_c = so_sell_c - combo_cost
                        p_pct_c = (p_c / combo_cost * 100) if combo_cost > 0 else 0
                        final_c = so_sell_c * (1 + GST_RATE)
                        col_c = "green" if p_pct_c >= 20 else "red"
                        st.markdown(
                            f"Final Customer Price (GST-incl.): **SGD {final_c:.2f}**<br>"
                            f"<span style='color:{col_c}'>Nominal Profit: **SGD {p_c:.2f}** "
                            f"({p_pct_c:.1f}%)</span>",
                            unsafe_allow_html=True,
                        )

                    cc1, cc2 = st.columns([2, 1])
                    with cc1:
                        if st.button("✅ Confirm — Add Combo", type="primary",
                                     key="so_combo_submit"):
                            if len(sel_labels_c) < 2:
                                st.error("A combo must include at least 2 different items.")
                            elif not so_name_c.strip():
                                st.error("Combo name is required.")
                            elif so_sell_c <= 0:
                                st.error("Selling price must be greater than zero.")
                            else:
                                try:
                                    upsert_selling_option(
                                        fr_id, so_name_c.strip(),
                                        option_type="bundle",
                                        composition=composition_c,
                                        selling_price=float(so_sell_c),
                                    )
                                    _reset_and_scroll(
                                        ["so_combo_items", "so_combo_name",
                                         "so_combo_price", "so_type_radio"],
                                        f"Combo '{so_name_c.strip()}' added.",
                                    )
                                except (ValidationError, Exception) as ex:
                                    st.error(f"Error: {ex}")

    # ── Submit to RF — bottom of Selling Options tab (spec G) ─────────────
    if (is_creator or is_committee_member) and status in ("draft", "rejected"):
        st.markdown("---")
        st.markdown("#### Submit Proposal for RF Review")
        st.caption(
            "Once you have completed all tabs, submit the proposal package to the RF. "
            "Appendix uploads (Marketing and Artwork) are encouraged but not required."
        )
        _fr_fresh = get_fundraiser(fr_id) or fr
        _submit_errors = validate_for_submission(_fr_fresh)

        if _submit_errors:
            st.warning("The following must be completed before submission:")
            for e in _submit_errors:
                st.markdown(f"- {e}")
        else:
            if st.button("📤 Submit to RF for Approval", type="primary",
                         key="wf_btn_submit_rf_selling"):
                st.session_state["wf_confirm_submit_rf_selling"] = True

        if st.session_state.get("wf_confirm_submit_rf_selling"):
            with st.container(border=True):
                st.markdown("**Submit this proposal to the RF for review?**")
                st.caption("You will not be able to edit it until the RF returns it.")
                ca, cb = st.columns(2)
                with ca:
                    if st.button("Yes, submit", type="primary",
                                 key="wf_yes_submit_rf_selling", use_container_width=True):
                        try:
                            transition_status(fr_id, "rf_review", by_user=user)
                            st.session_state.pop("wf_confirm_submit_rf_selling", None)
                            st.session_state["sh_action_msg"] = (
                                "success",
                                "Proposal submitted to the Resident Fellow for review.",
                            )
                            st.rerun()
                        except (InvalidTransition, Exception) as exc:
                            st.error(str(exc))
                with cb:
                    if st.button("Cancel", key="wf_no_submit_rf_selling",
                                 use_container_width=True):
                        st.session_state.pop("wf_confirm_submit_rf_selling", None)
                        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# APPENDIX SHARED RENDERER  (used by tabs 5 and 6)
# ══════════════════════════════════════════════════════════════════════════════

def _render_appendix(section: str, section_label: str) -> None:
    items_ref = list_items(fr_id)
    item_map_ref = {it["item_code"]: it.get("item_name") or it["item_code"]
                    for it in items_ref}
    assets = list_assets(fr_id, section=section)

    ASSET_TYPE_LABELS = {
        "product_design":  "Product / Item Design",
        "marketing_promo": "Marketing / Promotional Material",
        "other":           "Other",
    }

    st.caption(
        "Upload product designs and promotional materials for RF review. "
        "RF can visually inspect what is being sold and how it will be marketed. "
        "Images and PDFs are both accepted."
    )

    # ── Gallery ───────────────────────────────────────────────────────────
    if assets:
        st.markdown(
            f"#### {section_label} Gallery "
            f"({len(assets)} file{'s' if len(assets) != 1 else ''})"
        )
        cols_per_row = 3
        for row_start in range(0, len(assets), cols_per_row):
            row_assets = assets[row_start:row_start + cols_per_row]
            cols = st.columns(cols_per_row)
            for col, asset in zip(cols, row_assets):
                with col:
                    with st.container(border=True):
                        mime = asset.get("file_mime") or ""
                        is_image = mime.startswith("image/") or asset["file_name"].lower().endswith(
                            (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")
                        )
                        if is_image:
                            try:
                                st.image(asset["file_url"], use_container_width=True)
                            except Exception:
                                st.markdown("🖼️ *Image preview unavailable*")
                        else:
                            st.markdown(
                                "<div style='background:#fef2f2;border-radius:6px;"
                                "padding:2rem 0;text-align:center;font-size:2.5rem;'>"
                                "📄</div>",
                                unsafe_allow_html=True,
                            )
                            st.markdown(
                                f"<a href='{asset['file_url']}' target='_blank' "
                                f"style='font-size:0.78rem;'>Open PDF</a>",
                                unsafe_allow_html=True,
                            )

                        atype_label = ASSET_TYPE_LABELS.get(
                            asset["asset_type"], asset["asset_type"]
                        )
                        badge_cls = {
                            "product_design": "product",
                            "marketing_promo": "marketing",
                            "other": "other",
                        }.get(asset["asset_type"], "other")
                        linked_name = item_map_ref.get(
                            asset.get("linked_item_code") or "", ""
                        )

                        st.markdown(
                            f"<div class='sh-gallery-title'>{asset['title']}</div>"
                            + (
                                f"<div class='sh-gallery-desc'>{asset.get('description', '')}</div>"
                                if asset.get("description") else ""
                            )
                            + f"<span class='sh-gallery-badge {badge_cls}'>{atype_label}</span>"
                            + (
                                f"<br><span style='font-size:0.75rem;color:#64748b;'>"
                                f"📦 {linked_name}</span>"
                                if linked_name else ""
                            ),
                            unsafe_allow_html=True,
                        )

                        if can_edit_appendix:
                            ea, eb = st.columns(2)
                            with ea:
                                if st.button("✏️ Edit",
                                             key=f"edit_asset_{asset['id']}",
                                             use_container_width=True):
                                    st.session_state[f"sh_edit_asset_{section}"] = asset["id"]
                                    st.rerun()
                            with eb:
                                if st.button("🗑️ Delete",
                                             key=f"del_asset_{asset['id']}",
                                             use_container_width=True):
                                    st.session_state[f"sh_del_asset_{section}"] = asset["id"]
                                    st.rerun()

                        # Edit metadata panel
                        if st.session_state.get(f"sh_edit_asset_{section}") == asset["id"]:
                            with st.container(border=True):
                                new_title = st.text_input(
                                    "Title", value=asset["title"],
                                    key=f"ea_title_{asset['id']}"
                                )
                                new_desc = st.text_area(
                                    "Description",
                                    value=asset.get("description") or "",
                                    key=f"ea_desc_{asset['id']}"
                                )
                                new_atype = st.selectbox(
                                    "Type",
                                    list(ASSET_TYPE_LABELS.keys()),
                                    format_func=lambda x: ASSET_TYPE_LABELS[x],
                                    index=list(ASSET_TYPE_LABELS.keys()).index(
                                        asset["asset_type"]
                                    ),
                                    key=f"ea_type_{asset['id']}",
                                )
                                new_linked = None
                                if new_atype == "product_design":
                                    linked_opts = [""] + list(item_map_ref.keys())
                                    linked_fmt = {"": "(none)", **item_map_ref}
                                    cur_link = asset.get("linked_item_code") or ""
                                    sel_link = st.selectbox(
                                        "Linked Item *",
                                        linked_opts,
                                        format_func=lambda x: linked_fmt.get(x, x),
                                        index=(
                                            linked_opts.index(cur_link)
                                            if cur_link in linked_opts else 0
                                        ),
                                        key=f"ea_link_{asset['id']}",
                                    )
                                    new_linked = sel_link or None
                                else:
                                    linked_opts_m = [""] + list(item_map_ref.keys())
                                    linked_fmt_m = {
                                        "": "(general project)", **item_map_ref
                                    }
                                    cur_link_m = asset.get("linked_item_code") or ""
                                    sel_link_m = st.selectbox(
                                        "Associated item (optional)",
                                        linked_opts_m,
                                        format_func=lambda x: linked_fmt_m.get(x, x),
                                        index=(
                                            linked_opts_m.index(cur_link_m)
                                            if cur_link_m in linked_opts_m else 0
                                        ),
                                        key=f"ea_link_m_{asset['id']}",
                                    )
                                    new_linked = sel_link_m or None

                                cs1, cs2 = st.columns(2)
                                with cs1:
                                    if st.button("💾 Save", type="primary",
                                                  key=f"ea_save_{asset['id']}"):
                                        if not new_title.strip():
                                            st.error("Title is required.")
                                        else:
                                            try:
                                                update_asset_metadata(
                                                    asset["id"],
                                                    title=new_title,
                                                    description=new_desc,
                                                    asset_type=new_atype,
                                                    linked_item_code=new_linked,
                                                )
                                                st.session_state.pop(
                                                    f"sh_edit_asset_{section}", None
                                                )
                                                st.success("Metadata updated.")
                                                st.rerun()
                                            except Exception as ex:
                                                st.error(f"Error: {ex}")
                                with cs2:
                                    if st.button("Cancel",
                                                  key=f"ea_cancel_{asset['id']}"):
                                        st.session_state.pop(
                                            f"sh_edit_asset_{section}", None
                                        )
                                        st.rerun()

                        # Delete confirmation
                        if st.session_state.get(f"sh_del_asset_{section}") == asset["id"]:
                            st.warning(f"Delete **{asset['title']}**?")
                            dd1, dd2 = st.columns(2)
                            with dd1:
                                if st.button("Yes, delete", type="primary",
                                              key=f"da_yes_{asset['id']}"):
                                    try:
                                        delete_asset(asset["id"])
                                        st.session_state.pop(
                                            f"sh_del_asset_{section}", None
                                        )
                                        st.success("Deleted.")
                                        st.rerun()
                                    except Exception as ex:
                                        st.error(f"Error: {ex}")
                            with dd2:
                                if st.button("Cancel", key=f"da_no_{asset['id']}"):
                                    st.session_state.pop(
                                        f"sh_del_asset_{section}", None
                                    )
                                    st.rerun()
    else:
        st.markdown(
            "<div class='sh-empty'><div class='sh-empty-icon'>🖼️</div>"
            "<div class='sh-empty-title'>No files uploaded yet</div>"
            "<div class='sh-empty-text'>Upload product designs and marketing materials below "
            "so RF can visually review what is being sold and how it will be advertised.</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    # ── Upload form ────────────────────────────────────────────────────────
    if can_edit_appendix:
        st.markdown("---")
        st.markdown(f"#### Upload to {section_label}")

        uploaded_file = st.file_uploader(
            "Select file (image or PDF)",
            type=["jpg", "jpeg", "png", "gif", "webp", "pdf"],
            key=f"uploader_{section}",
            help="Drag and drop or click to browse. Max recommended size: 10 MB.",
        )

        if uploaded_file is not None:
            with st.container(border=True):
                st.markdown("**File details — complete before uploading:**")
                up_title = st.text_input(
                    "Title *", key=f"up_title_{section}",
                    placeholder="e.g. T-shirt Design v2, Instagram Poster",
                )
                up_desc = st.text_area(
                    "Description *", key=f"up_desc_{section}", height=80,
                    placeholder="Brief description of what this file shows.",
                )
                up_type = st.selectbox(
                    "File type *",
                    list(ASSET_TYPE_LABELS.keys()),
                    format_func=lambda x: ASSET_TYPE_LABELS[x],
                    key=f"up_type_{section}",
                )
                up_linked = None
                if up_type == "product_design":
                    if item_map_ref:
                        linked_opts_u = list(item_map_ref.keys())
                        sel_linked_u = st.selectbox(
                            "Linked Item * (required for product designs)",
                            linked_opts_u,
                            format_func=lambda x: item_map_ref.get(x, x),
                            key=f"up_linked_{section}",
                        )
                        up_linked = sel_linked_u
                    else:
                        st.warning(
                            "Register items in the Items tab first to link a product design."
                        )
                else:
                    if item_map_ref:
                        linked_opts_u2 = [""] + list(item_map_ref.keys())
                        linked_fmt_u2 = {
                            "": "(general project — no specific item)", **item_map_ref
                        }
                        sel_linked_u2 = st.selectbox(
                            "Associated item (optional)",
                            linked_opts_u2,
                            format_func=lambda x: linked_fmt_u2.get(x, x),
                            key=f"up_linked_opt_{section}",
                        )
                        up_linked = sel_linked_u2 or None

                cu1, cu2 = st.columns([2, 1])
                with cu1:
                    if st.button("⬆️ Upload & Save", type="primary",
                                  key=f"do_upload_{section}"):
                        if not up_title.strip():
                            st.error("Title is required.")
                        elif not up_desc.strip():
                            st.error("Description is required.")
                        elif up_type == "product_design" and not up_linked and item_map_ref:
                            st.error("Please link this design to a registered item.")
                        else:
                            try:
                                file_bytes = uploaded_file.read()
                                create_asset(
                                    fr_id,
                                    section=section,
                                    asset_type=up_type,
                                    title=up_title.strip(),
                                    description=up_desc.strip(),
                                    file_name=uploaded_file.name,
                                    file_bytes=file_bytes,
                                    file_mime=uploaded_file.type,
                                    linked_item_code=up_linked or None,
                                    created_by_id=user["id"],
                                )
                                st.success(f"'{up_title}' uploaded successfully.")
                                st.rerun()
                            except FundraiserError as ex:
                                st.error(str(ex))
                            except Exception as ex:
                                st.error(f"Upload failed: {ex}")
                with cu2:
                    st.markdown("<div style='height:1.9rem;'></div>", unsafe_allow_html=True)
                    st.caption("Files are saved to secure storage.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — APPENDIX MARKETING
# ══════════════════════════════════════════════════════════════════════════════

with tab_mkt:
    _render_appendix("marketing", "Appendix Marketing")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — APPENDIX ARTWORK
# ══════════════════════════════════════════════════════════════════════════════

with tab_art:
    _render_appendix("artwork", "Appendix Artwork")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — STOCK MOVEMENT  (only after Master approval — spec F3/F4)
# ══════════════════════════════════════════════════════════════════════════════

if tab_stock:
    with tab_stock:
        opts_sm = list_selling_options(fr_id)
        movements = {m["selling_option_id"]: m for m in list_stock_movements(fr_id)}

        if not opts_sm:
            st.warning(
                "No selling options registered. Add them in the Selling Options tab first."
            )
        else:
            st.markdown("#### Record Quantities Sold")
            st.caption(
                "Enter the actual number of units sold for each selling option. "
                "These figures drive all downstream financial calculations."
            )

            for o in opts_sm:
                mv = movements.get(o["id"])
                cur_qty = int(mv["quantity_sold"]) if mv else 0
                sp = float(o["selling_price"])
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                    with c1:
                        st.markdown(f"**{o['option_name']}**")
                        st.caption(o["option_type"].capitalize())
                    with c2:
                        new_qty = st.number_input(
                            "Qty Sold", value=cur_qty, min_value=0,
                            key=f"sm_qty_{o['id']}",
                            disabled=not can_edit_report,
                        )
                    with c3:
                        rev = new_qty * sp
                        st.markdown(f"Gross Revenue<br>**SGD {rev:.2f}**",
                                    unsafe_allow_html=True)
                    with c4:
                        gst = rev * GST_RATE
                        st.markdown(f"GST Collected<br>**SGD {gst:.2f}**",
                                    unsafe_allow_html=True)
                    if can_edit_report and st.button("💾 Save", key=f"sm_save_{o['id']}"):
                        try:
                            upsert_stock_movement(fr_id, o["id"], int(new_qty))
                            st.success("Saved.")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Error: {ex}")

            st.markdown("---")
            st.markdown("#### Stock Reconciliation")
            recon = compute_stock_reconciliation(fr_id)
            if recon:
                for row in recon:
                    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                    with c1:
                        st.markdown(f"**{row.item_name or row.item_code}**")
                    with c2:
                        st.caption(f"Purchased: {row.purchased}")
                    with c3:
                        st.caption(f"Sold (via options): {row.sold}")
                    with c4:
                        clr = "red" if row.over_sold else "#059669"
                        st.markdown(
                            f"<span style='color:{clr};font-weight:600;'>"
                            f"Remaining: {row.unsold}</span>",
                            unsafe_allow_html=True,
                        )

            st.markdown("---")
            st.markdown("#### Financial Summary")
            summary = compute_financial_summary(fr_id)
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total Cost", f"SGD {float(summary.total_cost):.2f}")
            c2.metric("Gross Revenue (before GST)",
                      f"SGD {float(summary.gross_revenue_before_gst):.2f}")
            c3.metric("GST Collected", f"SGD {float(summary.gst_collected):.2f}")
            c4.metric("Total Customer Payment",
                      f"SGD {float(summary.total_customer_payment):.2f}")
            c5.metric("Gross Profit / Net Available",
                      f"SGD {float(summary.gross_profit):.2f}")
            st.caption(
                "Gross Revenue (before GST) is the Committee's actual earnings. "
                "GST Collected is tax remitted to the government — it is NOT profit."
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 8 — REPORT CONFIRMATIONS  (reporting / closure stages only)
# ══════════════════════════════════════════════════════════════════════════════

if tab_report:
    with tab_report:
        st.markdown("#### Financial Statement")
        summary_rc = compute_financial_summary(fr_id)
        gsr = float(summary_rc.gross_revenue_before_gst)
        gst_a = float(summary_rc.gst_collected)
        tcp = float(summary_rc.total_customer_payment)
        tc = float(summary_rc.total_cost)
        gp = float(summary_rc.gross_profit)

        st.markdown(
            f"<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;"
            f"padding:1rem 1.5rem;margin-bottom:1rem;'>"
            f"<p style='margin:0 0 0.5rem 0;font-weight:600;color:#0f172a;'>"
            f"Financial Acknowledgement</p>"
            f"<p style='margin:0;color:#334155;font-size:0.9rem;'>"
            f"The Committee acknowledges that the Selling Price displayed to customers "
            f"<b>excludes GST</b>. Customers pay an additional 9% GST which is collected on "
            f"behalf of the government. <b>This GST is not part of the Committee's profit.</b></p>"
            f"<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;"
            f"margin-top:1rem;'>"
            f"<div><div style='font-size:0.75rem;color:#64748b;text-transform:uppercase;"
            f"letter-spacing:.04em;'>Gross Revenue (before GST)</div>"
            f"<div style='font-size:1.4rem;font-weight:700;color:#0f172a;'>"
            f"SGD {gsr:.2f}</div></div>"
            f"<div><div style='font-size:0.75rem;color:#64748b;text-transform:uppercase;"
            f"letter-spacing:.04em;'>GST Collected (→ government)</div>"
            f"<div style='font-size:1.4rem;font-weight:700;color:#dc2626;'>"
            f"SGD {gst_a:.2f}</div></div>"
            f"<div><div style='font-size:0.75rem;color:#64748b;text-transform:uppercase;"
            f"letter-spacing:.04em;'>Total Customer Payment</div>"
            f"<div style='font-size:1.4rem;font-weight:700;color:#0f172a;'>"
            f"SGD {tcp:.2f}</div></div>"
            f"<div><div style='font-size:0.75rem;color:#64748b;text-transform:uppercase;"
            f"letter-spacing:.04em;'>Total Cost (items)</div>"
            f"<div style='font-size:1.4rem;font-weight:700;color:#0f172a;'>"
            f"SGD {tc:.2f}</div></div>"
            f"<div><div style='font-size:0.75rem;color:#64748b;text-transform:uppercase;"
            f"letter-spacing:.04em;'>Gross Profit / Net Amount Available</div>"
            f"<div style='font-size:1.4rem;font-weight:700;color:#10b981;'>"
            f"SGD {gp:.2f}</div></div>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

        st.markdown("---")
        can_do_rf = ((_is_rf and is_rf_in_charge) or _is_master) and status == "reporting"
        current_checklist: dict = fr.get("rf_checklist") or {}

        st.markdown("#### RF Closure Checklist")
        st.caption("The RF in charge must confirm all items below before submitting closure.")

        groups = {
            "📊 Financial Checks": [
                "financial_reviewed", "nusync_only", "no_personal_accts", "gst_acknowledged"
            ],
            "📦 Stock & Inventory": ["stock_accounted", "sales_recorded", "unsold_noted"],
            "📌 Administrative":   ["flyers_removed"],
        }
        new_checklist: dict[str, bool] = dict(current_checklist)

        for group_label, keys in groups.items():
            st.markdown(f"**{group_label}**")
            for k in keys:
                label_text = RF_CHECKLIST_ITEMS[k]
                checked = current_checklist.get(k, False)
                new_val = st.checkbox(
                    label_text,
                    value=checked,
                    key=f"rfcl_{k}",
                    disabled=not can_do_rf,
                )
                new_checklist[k] = new_val

        if can_do_rf:
            if st.button("💾 Save Checklist Progress", key="save_rf_checklist"):
                try:
                    update_rf_checklist(fr_id, new_checklist)
                    st.success("Checklist progress saved.")
                    _reload()
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error: {ex}")

        rf_confirmed = bool(fr.get("rf_confirmed_by"))
        if rf_confirmed:
            st.markdown(
                f"<div class='sh-sig-block'>"
                f"<div><div class='sh-sig-label'>RF Closure Confirmed by</div>"
                f"<div class='sh-sig-name'>{fr.get('rf_confirmed_by', '')}</div></div>"
                f"<div class='sh-sig-date'>{_fmt_date(fr.get('rf_confirmed_at'))}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown("#### Closure Confirmation Sequence")

        def _closure_sig_row(label: str, name_field: str, date_field: str,
                              is_pending: bool, can_confirm: bool,
                              confirm_key: str, confirm_new_status: str,
                              confirm_label: str) -> None:
            done = bool(fr.get(name_field))
            if done:
                st.markdown(
                    f"<div class='sh-sig-block sh-sig-done'>"
                    f"<div><div class='sh-sig-label'>✅ {label}</div>"
                    f"<div class='sh-sig-name'>{fr.get(name_field, '')}</div></div>"
                    f"<div class='sh-sig-date'>{_fmt_date(fr.get(date_field))}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            elif is_pending and can_confirm:
                with st.container(border=True):
                    st.markdown(f"**{label}**")
                    st.caption("Your confirmation is required to proceed to the next stage.")
                    if st.button(f"✅ {confirm_label}", type="primary", key=confirm_key):
                        st.session_state[f"wf_confirm_{confirm_key}"] = True
                    if st.session_state.get(f"wf_confirm_{confirm_key}"):
                        st.warning("Are you sure? This action cannot be undone.")
                        ca, cb = st.columns(2)
                        with ca:
                            if st.button("Yes, confirm", type="primary",
                                         key=f"wf_yes_{confirm_key}"):
                                try:
                                    transition_status(
                                        fr_id, confirm_new_status, by_user=user
                                    )
                                    st.session_state.pop(
                                        f"wf_confirm_{confirm_key}", None
                                    )
                                    st.session_state["sh_action_msg"] = (
                                        "success", f"{label} confirmed successfully."
                                    )
                                    st.rerun()
                                except Exception as ex:
                                    st.error(f"Error: {ex}")
                        with cb:
                            if st.button("Cancel", key=f"wf_no_{confirm_key}"):
                                st.session_state.pop(f"wf_confirm_{confirm_key}", None)
                                st.rerun()
            else:
                st.markdown(
                    f"<div style='padding:0.5rem 1rem;border:1px dashed #e2e8f0;"
                    f"border-radius:8px;color:#94a3b8;font-size:0.88rem;margin:0.3rem 0;'>"
                    f"⏳ {label} — pending</div>",
                    unsafe_allow_html=True,
                )

        rf_can_submit = can_do_rf and rf_checklist_complete(fr)
        if can_do_rf and not rf_checklist_complete(fr):
            st.warning("Complete all RF checklist items above before submitting RF closure.")

        if status == "reporting":
            with st.container(border=True):
                st.markdown("**1. RF Closure Submission**")
                if rf_can_submit:
                    if st.button("✅ Submit RF Closure", type="primary",
                                 key="submit_rf_closure"):
                        st.session_state["wf_confirm_rf_closure"] = True
                    if st.session_state.get("wf_confirm_rf_closure"):
                        st.warning(
                            "Submit RF closure? This will lock the checklist and notify DOF."
                        )
                        ca, cb = st.columns(2)
                        with ca:
                            if st.button("Yes, submit closure", type="primary",
                                         key="wf_yes_rf_closure"):
                                try:
                                    update_rf_checklist(fr_id, new_checklist)
                                    transition_status(fr_id, "dof_confirming", by_user=user)
                                    st.session_state.pop("wf_confirm_rf_closure", None)
                                    st.session_state["sh_action_msg"] = (
                                        "success",
                                        "RF closure submitted. Awaiting DOF confirmation.",
                                    )
                                    st.rerun()
                                except Exception as ex:
                                    st.error(f"Error: {ex}")
                        with cb:
                            if st.button("Cancel", key="wf_no_rf_closure"):
                                st.session_state.pop("wf_confirm_rf_closure", None)
                                st.rerun()
                else:
                    st.caption("Complete all RF checklist items to enable submission.")

        _closure_sig_row(
            label="2. DOF Confirmation",
            name_field="dof_confirmed_by",
            date_field="dof_confirmed_at",
            is_pending=status == "dof_confirming",
            can_confirm=_is_dof,
            confirm_key="dof_confirm",
            confirm_new_status="finance_confirming",
            confirm_label="DOF Confirm",
        )

        _closure_sig_row(
            label="3. Finance Confirmation",
            name_field="finance_confirmed_by",
            date_field="finance_confirmed_at",
            is_pending=status == "finance_confirming",
            can_confirm=_is_finance,
            confirm_key="finance_confirm",
            confirm_new_status="master_confirming",
            confirm_label="Finance Confirm",
        )

        _closure_sig_row(
            label="4. Master Final Confirmation",
            name_field="master_closure_by",
            date_field="master_closure_at",
            is_pending=status == "master_confirming",
            can_confirm=_is_master,
            confirm_key="master_final",
            confirm_new_status="closed",
            confirm_label="Master — Confirm & Release Funds",
        )

        if fr.get("funds_available") or status == "closed":
            st.markdown(
                "<div style='background:#d1fae5;border:2px solid #10b981;border-radius:10px;"
                "padding:1rem 1.5rem;margin-top:1rem;text-align:center;'>"
                "<div style='font-size:1.3rem;font-weight:700;color:#065f46;'>"
                "✅ FUNDS AVAILABLE — Fundraiser Fully Closed</div>"
                "<div style='color:#047857;font-size:0.9rem;margin-top:0.3rem;'>"
                "All confirmation stages completed. Net Amount is available to the Committee."
                "</div></div>",
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 9 — PURCHASER LIST  (staff only)
# ══════════════════════════════════════════════════════════════════════════════

if tab_purchaser:
    with tab_purchaser:
        st.markdown("#### Purchaser List")
        st.caption(
            "This section holds purchaser records once sales are executed via NUSync. "
            "Export from NUSync and attach here for record-keeping."
        )
        t7_notes = st.text_area(
            "Notes / reference",
            value=fr.get("proposal_extra") or "",
            height=100,
            disabled=not can_edit_report and not can_edit_proposal,
            key="t7_notes",
        )
        if (can_edit_proposal or can_edit_report) and st.button(
            "💾 Save Notes", key="t7_save"
        ):
            update_fundraiser_fields(fr_id, {"proposal_extra": t7_notes})
            st.success("Notes saved.")


# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOW ACTION BAR  (RF / Master actions; student Submit is in Selling Options tab)
# ══════════════════════════════════════════════════════════════════════════════

st.divider()
st.subheader("Workflow Actions")


def _confirm_and_transition(
    key: str, btn_label: str,
    new_status: str, confirm_q: str, after_msg: str,
    btn_type: str = "primary",
    pre_check_fn=None,
) -> None:
    if st.button(btn_label, type=btn_type, use_container_width=True,
                 key=f"wf_btn_{key}"):
        if pre_check_fn:
            errors = pre_check_fn()
            if errors:
                for e in errors:
                    st.error(e)
                return
        st.session_state[f"wf_confirm_{key}"] = True

    if st.session_state.get(f"wf_confirm_{key}"):
        with st.container(border=True):
            st.markdown(f"**{confirm_q}**")
            ca, cb = st.columns(2)
            with ca:
                if st.button("Yes, confirm", key=f"wf_yes_{key}",
                             type="primary", use_container_width=True):
                    try:
                        transition_status(fr_id, new_status, by_user=user)
                        st.session_state.pop(f"wf_confirm_{key}", None)
                        st.session_state["sh_action_msg"] = ("success", after_msg)
                        st.rerun()
                    except (InvalidTransition, Exception) as exc:
                        st.error(str(exc))
            with cb:
                if st.button("Cancel", key=f"wf_no_{key}", use_container_width=True):
                    st.session_state.pop(f"wf_confirm_{key}", None)
                    st.rerun()


action_cols = st.columns(5)

# RF → send to The Master
with action_cols[1]:
    if _is_rf and (is_rf_in_charge or is_staff()) and status == "rf_review":
        _confirm_and_transition(
            key="rf_to_master",
            btn_label="📨 Send to The Master",
            new_status="master_review",
            confirm_q="Forward this proposal to the Hall Master for final approval?",
            after_msg="Proposal forwarded to the Hall Master.",
        )

# Master → approve from master_review
with action_cols[2]:
    if _is_master and status == "master_review":
        _confirm_and_transition(
            key="master_approve",
            btn_label="✅ Approve",
            new_status="approved",
            confirm_q="Approve this fundraiser proposal?",
            after_msg="Proposal approved and ready for execution.",
        )

# Master → direct approve from rf_review (bypass RF→Master forwarding)
with action_cols[2]:
    if _is_master and status == "rf_review":
        _confirm_and_transition(
            key="master_direct_approve",
            btn_label="✅ Approve Directly",
            new_status="approved",
            confirm_q="Approve this proposal directly (bypassing the RF→Master step)?",
            after_msg="Proposal approved directly by The Master.",
        )

# RF / Master → return to student
with action_cols[3]:
    if (is_staff() or _is_rf) and status == "rf_review":
        _confirm_and_transition(
            key="request_changes",
            btn_label="↩ Return to Student",
            new_status="draft",
            confirm_q="Return this proposal to the student for revisions?",
            after_msg="Proposal returned to draft. The student can make changes.",
            btn_type="secondary",
        )

# Master → return to RF
with action_cols[3]:
    if _is_master and status == "master_review":
        _confirm_and_transition(
            key="delegate_rf",
            btn_label="↩ Return to RF",
            new_status="rf_review",
            confirm_q="Return this proposal to the RF for revisions?",
            after_msg="Proposal returned to RF.",
            btn_type="secondary",
        )

# Begin execution
with action_cols[4]:
    if status == "approved" and (is_staff() or is_creator):
        _confirm_and_transition(
            key="start_exec",
            btn_label="▶ Begin Execution",
            new_status="executing",
            confirm_q="Mark this fundraiser as in execution? Selling has started.",
            after_msg="Fundraiser is now in the execution phase.",
        )

# Move to reporting
with action_cols[4]:
    if status == "executing" and (is_staff() or is_creator):
        _confirm_and_transition(
            key="move_reporting",
            btn_label="📊 Move to Reporting",
            new_status="reporting",
            confirm_q="Move this fundraiser to the reporting phase? Selling is closed.",
            after_msg="Fundraiser moved to reporting phase.",
            btn_type="secondary",
        )


# ══════════════════════════════════════════════════════════════════════════════
# PDF EXPORT  (placed below workflow — not at the top of the page)
# ══════════════════════════════════════════════════════════════════════════════

st.divider()


def _generate_pdf(fundraiser: dict) -> bytes:
    try:
        from fpdf import FPDF
    except ImportError:
        return b""

    items_data = list_items(fr_id)
    opts_data = list_selling_options(fr_id)
    in_reporting = status not in ("draft", "rf_review", "master_review", "approved")
    summary = compute_financial_summary(fr_id) if in_reporting else None

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    def _sec(title: str) -> None:
        pdf.ln(5)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, title, ln=True)
        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 180, pdf.get_y())
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)

    def _row(label: str, value: str) -> None:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(60, 6, label, ln=False)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 6, value)

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, fundraiser["name"], ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Status: {STATUS_DISPLAY.get(status, status)}", ln=True)
    pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True)
    pdf.ln(2)

    _sec("1. Proposal Description")
    if fundraiser.get("objective"):
        _row("Description:", fundraiser["objective"])
    if fundraiser.get("beneficiary"):
        _row("Beneficiary:", fundraiser["beneficiary"])
    for label, field in [
        ("Marketing Start:", "marketing_start"), ("Marketing End:", "marketing_end"),
        ("Ordering Start:", "ordering_start"),   ("Ordering End:", "ordering_end"),
        ("Supplier Order:", "supplier_order_date"),
        ("Closing Date:",   "delivery_date"),
        ("Flyer Removal:",  "flyer_removal_date"),
        ("Report Deadline:","report_submission_deadline"),
        ("Flyer Remover:",  "flyer_remover_name"),
    ]:
        val = fundraiser.get(field)
        if val:
            _row(label, str(val))

    _sec("Compliance Confirmations")
    for key, label in [
        ("compliance_nusync",         "Funds collected via NUSync only"),
        ("compliance_no_intermediary", "No personal account intermediaries"),
        ("compliance_gst_artwork",    "GST statement included on all artwork"),
        ("compliance_regulations",    "NUS regulations acknowledged"),
    ]:
        tick = "☑" if fundraiser.get(key) else "☐"
        pdf.cell(0, 6, f"  {tick}  {label}", ln=True)

    if fundraiser.get("submitted_by_name"):
        pdf.ln(2)
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 6, (
            f"Submitted by: {fundraiser['submitted_by_name']}"
            f"  |  {_fmt_date(fundraiser.get('submitted_at'))}"
        ), ln=True)

    if items_data:
        _sec("2. Items to Purchase")
        pdf.set_font("Helvetica", "B", 9)
        for col, w in [("Item Name", 60), ("Supplier", 40), ("Qty", 18),
                        ("Unit Cost", 28), ("Total Cost", 34)]:
            pdf.cell(w, 6, col, border=1)
        pdf.ln()
        pdf.set_font("Helvetica", "", 9)
        grand = 0.0
        for it in items_data:
            nm = (it.get("item_name") or it["item_code"])[:35]
            qty = int(it["quantity"])
            uc = float(it["unit_cost"])
            tc = qty * uc
            grand += tc
            for val, w in [
                (nm, 60), ((it.get("supplier") or "")[:22], 40),
                (str(qty), 18), (f"SGD {uc:.2f}", 28), (f"SGD {tc:.2f}", 34),
            ]:
                pdf.cell(w, 6, val, border=1)
            pdf.ln()
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(146, 6, "Total Cost", border=1)
        pdf.cell(34, 6, f"SGD {grand:.2f}", border=1, ln=True)

    if opts_data:
        _sec("3. Selling Options")
        for o in opts_data:
            sp = float(o["selling_price"])
            uc = float(o["unit_cost"])
            profit = sp - uc
            profit_pct = (profit / uc * 100) if uc > 0 else 0
            final_price = sp * (1 + GST_RATE)
            comp = o.get("composition") or {}
            comp_str = ", ".join(f"{k}×{v}" for k, v in comp.items())
            pdf.multi_cell(0, 5, (
                f"  {o['option_name']}  [{o['option_type']}]   {comp_str}\n"
                f"  Unit Cost: SGD {uc:.2f}  |  Selling Price (before GST): SGD {sp:.2f}"
                f"  |  Final Customer Price (GST-incl.): SGD {final_price:.2f}\n"
                f"  Nominal Profit: SGD {profit:.2f}  ({profit_pct:.1f}%)"
            ))
            pdf.ln(1)

    if summary:
        _sec("4. Financial Summary")
        for label, val in [
            ("Total Cost:", f"SGD {float(summary.total_cost):.2f}"),
            ("Gross Revenue (before GST):",
             f"SGD {float(summary.gross_revenue_before_gst):.2f}"),
            ("GST Collected:", f"SGD {float(summary.gst_collected):.2f}"),
            ("Total Customer Payment:", f"SGD {float(summary.total_customer_payment):.2f}"),
            ("Gross Profit / Net Amount Available:",
             f"SGD {float(summary.gross_profit):.2f}"),
        ]:
            _row(label, val)

    sig_fields = [
        ("RF Approved by",       "rf_approved_by",       "rf_approved_at"),
        ("Master Approved by",   "master_approved_by",   "master_approved_at"),
        ("RF Confirmed by",      "rf_confirmed_by",      "rf_confirmed_at"),
        ("DOF Confirmed by",     "dof_confirmed_by",     "dof_confirmed_at"),
        ("Finance Confirmed by", "finance_confirmed_by", "finance_confirmed_at"),
        ("Master Closure by",    "master_closure_by",    "master_closure_at"),
    ]
    sigs = [(l, fundraiser.get(nb), _fmt_date(fundraiser.get(db)))
            for l, nb, db in sig_fields if fundraiser.get(nb)]
    if sigs:
        _sec("5. Approvals & Confirmations")
        for label, name, dt in sigs:
            pdf.cell(0, 6, f"  {label}: {name}  |  {dt}", ln=True)

    if fundraiser.get("funds_available"):
        pdf.ln(5)
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 9, "FUNDS AVAILABLE — Fundraiser Fully Closed", ln=True)

    return bytes(pdf.output())


_pdf_key = "sh_pdf_open"
if _pdf_key not in st.session_state:
    st.session_state[_pdf_key] = False

col_btn, _ = st.columns([1, 3])
with col_btn:
    if st.button(
        "✕ Cancel" if st.session_state[_pdf_key] else "📥 Export to PDF",
        key="sh_toggle_pdf",
        use_container_width=True,
    ):
        st.session_state[_pdf_key] = not st.session_state[_pdf_key]
        st.rerun()

if st.session_state[_pdf_key]:
    with st.container(border=True):
        st.caption("Download a PDF snapshot of this proposal at its current stage.")
        pdf_bytes = _generate_pdf(fr)
        if pdf_bytes:
            fname = f"fundraiser_{fr['name'].replace(' ', '_')}.pdf"
            st.download_button(
                "⬇️ Download PDF", data=pdf_bytes, file_name=fname,
                mime="application/pdf",
            )
        else:
            st.caption("PDF export is not available on this deployment.")


st.divider()
if st.button("← Back to Fundraisers"):
    st.switch_page("pages/10_Fundraisers.py")
