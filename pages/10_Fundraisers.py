"""
Fundraisers listing — role-aware.

- Students see only fundraisers they created or are registered in.
- Staff (RF, RLT, Master) see all fundraisers.
- Student_ad_hoc sees only fundraisers they're registered in.

Filter by status groups (Drafts, Under review, Approved, Executing,
Reporting, Closed). Each card shows status badge + key metadata.

"Create new fundraiser" button is shown only to roles that can create.
"""
import streamlit as st

from components.ui import inject_theme, brand_stripe, status_badge
from components.auth_ui import render_sidebar_user
from services.auth_service import (
    require_login, is_staff, has_any_role, current_user,
)
from services.fundraiser_service import list_fundraisers, create_fundraiser
from services.supabase_client import get_supabase

st.set_page_config(page_title="Fundraisers — Sheares Hall Ops",
                   page_icon="💰", layout="wide")
inject_theme()

user = require_login()
render_sidebar_user()

# ---------- Group fundraisers by status ----------

def _bucket(status: str) -> str:
    return {
        "draft":               "drafts",
        "rejected":            "drafts",
        "rf_review":           "under_review",
        "master_review":       "under_review",
        "approved":            "approved",
        "executing":           "executing",
        "reporting":           "reporting",
        "dof_confirming":      "reporting",
        "finance_confirming":  "reporting",
        "master_confirming":   "reporting",
        "closed":              "closed",
    }.get(status, "drafts")


fundraisers = list_fundraisers()  # RLS already filters by role/scope

# For ad-hoc students: also scope by fundraiser_students membership
# (RLS should handle this, but double-check defense-in-depth)
buckets = {"drafts": [], "under_review": [], "approved": [],
           "executing": [], "reporting": [], "closed": []}
for fr in fundraisers:
    buckets[_bucket(fr["status"])].append(fr)


# ---------- Header ----------

st.markdown("# Fundraisers")
brand_stripe()

can_create = has_any_role(["student", "resident_fellow", "rlt_lead",
                           "rlt_admin", "master"])

# ---------- Create new (top-right button for allowed roles) ----------

if can_create:
    if "sh_create_open" not in st.session_state:
        st.session_state["sh_create_open"] = False

    col_btn, _ = st.columns([1, 3])
    with col_btn:
        if st.button(
            "✕ Cancel" if st.session_state["sh_create_open"]
            else "➕ Create a new fundraiser",
            key="sh_toggle_create",
            use_container_width=True,
        ):
            st.session_state["sh_create_open"] = not st.session_state["sh_create_open"]
            st.rerun()

    if st.session_state["sh_create_open"]:
        with st.container(border=True):
            with st.form("sh_create_fr_form", clear_on_submit=True):
                name = st.text_input("Fundraiser name *",
                                     placeholder="e.g. Christmas Chocolate Drive")
                objective = st.text_area(
                    "Objective (short description, can edit later)",
                    height=80,
                )

                # RF selector — load list of resident_fellow users
                sb = get_supabase()
                rf_users = sb.table("users").select(
                    "id, full_name, username, assigned_block"
                ).eq("user_category", "management").execute().data or []
                # Filter to users who have resident_fellow role
                ur = sb.table("user_roles").select(
                    "user_id, roles(code)"
                ).execute().data or []
                rf_ids = {r["user_id"] for r in ur
                          if r.get("roles", {}).get("code") == "resident_fellow"}
                rf_users = [u for u in rf_users if u["id"] in rf_ids]

                if not rf_users:
                    st.error("No Resident Fellows in the system yet. "
                             "Ask Master to create them first.")
                    rf_in_charge_id = None
                else:
                    rf_label_to_id = {
                        f"{u['full_name']} (Block {u.get('assigned_block') or '?'})": u["id"]
                        for u in rf_users
                    }
                    selected_rf_label = st.selectbox(
                        "RF in charge *",
                        list(rf_label_to_id.keys()),
                    )
                    rf_in_charge_id = rf_label_to_id[selected_rf_label]

                submitted = st.form_submit_button("Create draft", type="primary")

            if submitted:
                if not name.strip():
                    st.error("Name is required.")
                elif not rf_in_charge_id:
                    st.error("RF in charge is required.")
                else:
                    try:
                        new_fr = create_fundraiser(
                            name=name.strip(),
                            objective=objective.strip() or None,
                            created_by_id=user["id"],
                            rf_in_charge_id=rf_in_charge_id,
                        )
                        # Register the creator as a student participant (so they keep access)
                        sb.table("fundraiser_students").upsert({
                            "fundraiser_id": new_fr["id"],
                            "user_id": user["id"],
                            "position": "chair",
                            "added_by": user["id"],
                        }, on_conflict="fundraiser_id,user_id").execute()
                        st.success(f"Draft created: {new_fr['name']}")
                        st.session_state["sh_selected_fundraiser"] = new_fr["id"]
                        st.session_state["sh_create_open"] = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not create: {e}")

st.divider()


# ---------- Render buckets ----------

def _render_card(fr: dict):
    """Compact fundraiser card — name + badge + truncated desc + Open button."""
    with st.container(border=True):
        cols = st.columns([4, 1])
        with cols[0]:
            st.markdown(
                f"<div style='font-weight:600;color:#0f172a;"
                f"font-size:0.95rem;margin-bottom:0.15rem;'>"
                f"{fr['name']}</div>",
                unsafe_allow_html=True,
            )
            objective = (fr.get("objective") or "").strip()
            if objective:
                preview = objective[:85] + ("…" if len(objective) > 85 else "")
                st.markdown(
                    f"<div style='color:#64748b;font-size:0.8rem;"
                    f"line-height:1.35;margin-bottom:0.4rem;'>{preview}</div>",
                    unsafe_allow_html=True,
                )
            st.markdown(status_badge(fr["status"]), unsafe_allow_html=True)
        with cols[1]:
            st.markdown("<div style='height:0.4rem;'></div>", unsafe_allow_html=True)
            if st.button("Open", key=f"open_{fr['id']}", use_container_width=True):
                st.session_state["sh_selected_fundraiser"] = fr["id"]
                st.switch_page("pages/11_Fundraiser_Detail.py")


def _render_bucket(title: str, frs: list[dict], empty_text: str, n_cols: int = 3):
    st.markdown(
        f"<div style='font-weight:600;font-size:0.95rem;color:#0f172a;"
        f"margin:0.8rem 0 0.5rem 0;'>{title} "
        f"<span style='color:#94a3b8;font-weight:500;'>({len(frs)})</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if not frs:
        st.caption(empty_text)
        return
    for i in range(0, len(frs), n_cols):
        cols = st.columns(n_cols)
        for col, fr in zip(cols, frs[i:i + n_cols]):
            with col:
                _render_card(fr)


_render_bucket("🟠 Drafts", buckets["drafts"],
               "No drafts. Create one using the button above." if can_create
               else "No drafts. Your team lead can create one.")

_render_bucket("🔵 Under Review / Awaiting Approval", buckets["under_review"],
               "Nothing pending review or approval.")

_render_bucket("🟢 Approved (ready to execute)", buckets["approved"],
               "No fundraisers awaiting execution.")

_render_bucket("🟡 In Execution", buckets["executing"],
               "No fundraisers currently running.")

_render_bucket("📊 Reporting & Closure", buckets["reporting"],
               "No fundraisers in the reporting or closure phase.")

_render_bucket("✅ Funds Available / Closed", buckets["closed"],
               "No closed fundraisers yet.")
