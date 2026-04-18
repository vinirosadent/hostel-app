"""
Fundraiser detail — 4 tabs + timeline + workflow buttons.

This is the SKELETON. Tabs 1-3 show only the essential fields for now;
the full form (items, selling options, stock, comments, signatures, PDF)
comes in the next dedicated session.

Permission logic:
  - Student / creator: edit only while status is 'draft' or 'rejected'.
  - Staff: can always view; can edit in hands-on mode (all fundraisers
    default to hands-on per user request).
  - Master: approves after RF.
"""
from datetime import datetime

import streamlit as st

from components.ui import inject_theme, brand_stripe, status_badge, timeline
from components.auth_ui import render_sidebar_user
from services.auth_service import (
    require_login, is_staff, is_master, has_role, current_user,
)
from services.fundraiser_service import (
    get_fundraiser, update_fundraiser_fields, transition_status,
    list_items, upsert_item, delete_item,
    list_selling_options, upsert_selling_option, delete_selling_option,
    compute_financial_summary, InvalidTransition, ValidationError,
)
from services.supabase_client import get_supabase

st.set_page_config(page_title="Fundraiser — Sheares Hall Ops",
                   page_icon="💰", layout="wide")
inject_theme()

user = require_login()
render_sidebar_user()


# ---------- Resolve which fundraiser to show ----------

fr_id = st.session_state.get("sh_selected_fundraiser")
if not fr_id:
    st.info("No fundraiser selected. Open one from the Fundraisers list.")
    if st.button("← Back to Fundraisers"):
        st.switch_page("pages/10_Fundraisers.py")
    st.stop()

fr = get_fundraiser(fr_id)
if not fr:
    st.error("Fundraiser not found or you don't have access.")
    if st.button("← Back"):
        st.switch_page("pages/10_Fundraisers.py")
    st.stop()


# ---------- Derived permissions ----------

status = fr["status"]
is_creator = fr["created_by_id"] == user["id"]
is_rf_in_charge = fr["rf_in_charge_id"] == user["id"]

# In hands-on mode, staff can always edit.
# Student can edit only in draft/rejected.
can_edit_proposal = (
    is_staff()
    or (is_creator and status in ("draft", "rejected"))
)
can_edit_report = (
    is_staff()
    or (is_creator and status in ("executing", "reporting"))
)


# ---------- Header ----------

col_title, col_status = st.columns([4, 1])
with col_title:
    st.markdown(f"# {fr['name']}")
with col_status:
    st.markdown(status_badge(status), unsafe_allow_html=True)

brand_stripe()

if fr.get("objective"):
    st.caption(fr["objective"])


# ---------- Timeline of workflow ----------

def build_timeline() -> list[dict]:
    """Build timeline items based on current status."""
    stages = [
        ("draft",     "Draft created"),
        ("rf_review", "Under RF review"),
        ("approved",  "Approved by Master"),
        ("executing", "In execution"),
        ("reporting", "Reporting phase"),
        ("closed",    "Closed"),
    ]
    # State order index
    order = {s[0]: i for i, s in enumerate(stages)}
    current_idx = order.get(status, 0)

    items = []
    for idx, (code, title) in enumerate(stages):
        if status == "rejected":
            state = "rejected" if idx == 0 else "pending"
        elif idx < current_idx:
            state = "completed"
        elif idx == current_idx:
            state = "current"
        else:
            state = "pending"
        items.append({"title": title, "meta": "", "state": state})
    return items


with st.expander("📍 Workflow status", expanded=True):
    st.markdown(timeline(build_timeline()), unsafe_allow_html=True)


# ---------- 4 tabs ----------

tab1, tab2, tab3, tab4 = st.tabs([
    "1. Description",
    "2. Items to purchase",
    "3. Selling options",
    "4. Report & stock",
])


# ======================================================================
# TAB 1 — Description
# ======================================================================

with tab1:
    with st.form("sh_tab1_form"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Fundraiser name",
                                 value=fr["name"],
                                 disabled=not can_edit_proposal)
            objective = st.text_area(
                "Objective", value=fr.get("objective") or "",
                disabled=not can_edit_proposal, height=120,
            )
            marketing_plan = st.text_area(
                "Marketing plan",
                value=fr.get("marketing_plan") or "",
                disabled=not can_edit_proposal, height=100,
            )
        with c2:
            marketing_start = st.date_input(
                "Marketing start",
                value=fr.get("marketing_start"),
                disabled=not can_edit_proposal,
            )
            marketing_end = st.date_input(
                "Marketing end",
                value=fr.get("marketing_end"),
                disabled=not can_edit_proposal,
            )
            delivery_date = st.date_input(
                "Delivery date",
                value=fr.get("delivery_date"),
                disabled=not can_edit_proposal,
            )

        if can_edit_proposal:
            save_tab1 = st.form_submit_button("Save Description",
                                              type="primary")
            if save_tab1:
                try:
                    update_fundraiser_fields(fr_id, {
                        "name": name,
                        "objective": objective,
                        "marketing_plan": marketing_plan,
                        "marketing_start": str(marketing_start) if marketing_start else None,
                        "marketing_end": str(marketing_end) if marketing_end else None,
                        "delivery_date": str(delivery_date) if delivery_date else None,
                    })
                    st.success("Description saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Save failed: {e}")
        else:
            st.form_submit_button("Read-only", disabled=True)
            st.caption("This fundraiser is locked for editing in its current state.")


# ======================================================================
# TAB 2 — Items to purchase
# ======================================================================

with tab2:
    st.caption(
        "List every item you plan to buy. Unit cost is what you pay the "
        "supplier. Total is auto-calculated. Items over SGD 1000 require a quote."
    )
    items = list_items(fr_id)

    if items:
        import pandas as pd
        rows = [{
            "Code": it["item_code"],
            "Supplier": it.get("supplier") or "—",
            "Qty": it["quantity"],
            "Unit cost (SGD)": float(it["unit_cost"]),
            "Total (SGD)": float(it.get("total_cost") or 0),
            "Quote needed?": "⚠️ Yes" if it.get("requires_quote") else "—",
        } for it in items]
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     use_container_width=True)

    if can_edit_proposal:
        with st.expander("➕ Add or update an item"):
            with st.form("sh_item_form", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    item_code = st.text_input("Item code (e.g. A)")
                    supplier = st.text_input("Supplier")
                with c2:
                    item_name = st.text_input("Item name (optional)")
                    quantity = st.number_input("Quantity", min_value=0, value=0)
                with c3:
                    unit_cost = st.number_input(
                        "Unit cost (SGD)", min_value=0.0,
                        value=0.0, format="%.2f",
                    )
                submitted = st.form_submit_button("Save item", type="primary")

            if submitted:
                try:
                    upsert_item(
                        fr_id, item_code,
                        item_name=item_name or None,
                        supplier=supplier or None,
                        quantity=int(quantity), unit_cost=float(unit_cost),
                    )
                    st.success(f"Item {item_code.upper()} saved.")
                    st.rerun()
                except (ValidationError, Exception) as e:
                    st.error(f"Save failed: {e}")

        if items:
            with st.expander("🗑️ Delete an item"):
                item_to_del = st.selectbox(
                    "Select item to delete",
                    [it["item_code"] for it in items],
                )
                if st.button("Confirm delete", type="secondary"):
                    target = next(it for it in items if it["item_code"] == item_to_del)
                    delete_item(target["id"])
                    st.success(f"Item {item_to_del} deleted.")
                    st.rerun()


# ======================================================================
# TAB 3 — Selling options (singles + bundles)
# ======================================================================

with tab3:
    st.caption(
        "Define how items will be sold — individually (singles) or "
        "grouped (bundles). Minimum margin target is 30%."
    )
    options = list_selling_options(fr_id)
    items_for_bundles = list_items(fr_id)

    if options:
        import pandas as pd
        rows = [{
            "Option": o["option_name"],
            "Type": o["option_type"],
            "Composition": ", ".join(
                f"{k}×{v}" for k, v in (o.get("composition") or {}).items()
            ),
            "Unit cost": float(o["unit_cost"]),
            "Sell price": float(o["selling_price"]),
            "Profit": float(o.get("profit") or 0),
            "Margin": f"{float(o.get('profit_margin') or 0)*100:.1f}%",
            "OK?": "✓" if o.get("is_acceptable") else "⚠",
        } for o in options]
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     use_container_width=True)

    if can_edit_proposal:
        if not items_for_bundles:
            st.info("Add items in Tab 2 before creating selling options.")
        else:
            with st.expander("➕ Add or update a selling option"):
                with st.form("sh_option_form", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        option_name = st.text_input("Option name (e.g. Single A, Bundle 1)")
                        option_type = st.selectbox("Type", ["single", "bundle"])
                    with c2:
                        selling_price = st.number_input(
                            "Selling price (SGD)", min_value=0.0,
                            value=0.0, format="%.2f",
                        )
                    st.caption("Composition — enter quantity per item code:")
                    composition = {}
                    cols = st.columns(min(4, len(items_for_bundles)))
                    for i, it in enumerate(items_for_bundles):
                        with cols[i % len(cols)]:
                            qty = st.number_input(
                                f"{it['item_code']}", min_value=0, value=0,
                                key=f"comp_{it['item_code']}",
                            )
                            if qty > 0:
                                composition[it["item_code"]] = int(qty)

                    submitted = st.form_submit_button("Save option", type="primary")

                if submitted:
                    try:
                        upsert_selling_option(
                            fr_id, option_name,
                            option_type=option_type,
                            composition=composition,
                            selling_price=float(selling_price),
                        )
                        st.success(f"Option '{option_name}' saved.")
                        st.rerun()
                    except (ValidationError, Exception) as e:
                        st.error(f"Save failed: {e}")


# ======================================================================
# TAB 4 — Report & stock (skeleton only)
# ======================================================================

with tab4:
    if status not in ("executing", "reporting", "closed"):
        st.info(
            "📊 The report tab unlocks once the fundraiser is in execution "
            "or reporting phase. Currently in '" + status + "'."
        )
    else:
        st.caption("Report the campaign outcomes.")
        summary = compute_financial_summary(fr_id)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total cost", f"SGD {float(summary.total_cost):.2f}")
        c2.metric("Actual revenue",
                  f"SGD {float(summary.actual_revenue):.2f}")
        c3.metric("Actual profit",
                  f"SGD {float(summary.actual_profit):.2f}")
        c4.metric("Profit after GST",
                  f"SGD {float(summary.profit_after_gst):.2f}")
        st.info(
            "Stock movement editor and closing checklist come in the next "
            "development iteration."
        )


st.divider()

# ======================================================================
# Workflow action bar
# ======================================================================

st.subheader("Workflow actions")

action_cols = st.columns(5)

# STUDENT: submit for RF review
with action_cols[0]:
    if is_creator and status in ("draft", "rejected"):
        if st.button("📤 Submit to RF", type="primary",
                     use_container_width=True):
            try:
                transition_status(fr_id, "rf_review")
                st.success("Submitted for RF review.")
                st.rerun()
            except InvalidTransition as e:
                st.error(str(e))

# RF: approve proposal (after review)
with action_cols[1]:
    if has_role("resident_fellow") and status == "rf_review" and is_rf_in_charge:
        if st.button("✓ Approve (RF)", type="primary", use_container_width=True):
            try:
                # RF approves -> goes to approved (Master will act next)
                # But the approval flow expects Master to be the one flipping to 'approved'
                # For MVP we keep RF moving forward to approved state;
                # Master's step is tracked via signatures table in next iteration.
                transition_status(fr_id, "approved")
                st.success("Approved by RF. Master will review and finalize.")
                st.rerun()
            except InvalidTransition as e:
                st.error(str(e))

# MASTER: start execution
with action_cols[2]:
    if is_master() and status == "approved":
        if st.button("▶ Start execution", type="primary",
                     use_container_width=True):
            try:
                transition_status(fr_id, "executing")
                st.success("Fundraiser is now in execution.")
                st.rerun()
            except InvalidTransition as e:
                st.error(str(e))

# Anyone with rights: reject with bounce to draft
with action_cols[3]:
    if is_staff() and status == "rf_review":
        if st.button("⟲ Request changes", use_container_width=True):
            try:
                transition_status(fr_id, "draft")
                st.success("Returned to draft for edits.")
                st.rerun()
            except InvalidTransition as e:
                st.error(str(e))

# CREATOR or staff: move to reporting
with action_cols[4]:
    if status == "executing" and (is_creator or is_staff()):
        if st.button("📊 Move to reporting", use_container_width=True):
            try:
                transition_status(fr_id, "reporting")
                st.success("Moved to reporting phase.")
                st.rerun()
            except InvalidTransition as e:
                st.error(str(e))

# CLOSE from reporting
for_close = st.columns(1)[0]
with for_close:
    if is_staff() and status == "reporting":
        if st.button("🔒 Close fundraiser", type="secondary"):
            try:
                transition_status(fr_id, "closed")
                st.success("Fundraiser closed.")
                st.rerun()
            except InvalidTransition as e:
                st.error(str(e))


st.divider()
if st.button("← Back to Fundraisers list"):
    st.switch_page("pages/10_Fundraisers.py")
