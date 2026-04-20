"""
Sheares Hall Ops — entry point.
"""
import streamlit as st

from services.auth_service import (
    current_user, is_authenticated, has_any_role,
)
from components.ui import inject_theme
from components.auth_ui import render_login_screen, render_sidebar_user

st.set_page_config(
    page_title="Sheares Hall Ops",
    page_icon="🟠",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_theme()

if not is_authenticated():
    render_login_screen()
    st.stop()

render_sidebar_user()

user = current_user()
user_name = user["full_name"]
user_roles = user.get("roles") or []

role_label_map = {
    "master": "Hall Master",
    "rlt_lead": "RLT Lead",
    "rlt_finan": "RLT Finance",
    "rlt_admin": "RLT Admin",
    "resident_fellow": "Resident Fellow",
    "student": "Student",
    "student_ad_hoc": "Student (Ad-hoc)",
}
role_display = " · ".join(role_label_map.get(r, r) for r in user_roles) or "Member"

# ── Password warning ──────────────────────────────────────────
if user.get("must_change_password"):
    st.warning("🔐 **Temporary password active.** Change it in the sidebar → Change Password.")

# ── Header ────────────────────────────────────────────────────
st.markdown(
    f"<h1 style='color:#0f172a;margin-bottom:0;'>Welcome, {user_name}</h1>"
    f"<p style='color:#64748b;font-size:0.95rem;margin-top:0.2rem;'>{role_display} · Sheares Hall Ops</p>",
    unsafe_allow_html=True,
)
st.markdown('<div style="height:4px;background:linear-gradient(90deg,#ea7a1e,#f59e0b);border-radius:2px;max-width:140px;margin:0.5rem 0 1.5rem 0;"></div>', unsafe_allow_html=True)


# ── Module cards ──────────────────────────────────────────────

def _can(roles: list[str] | None) -> bool:
    return True if not roles else has_any_role(roles)


MODULES = [
    {
        "icon": "💰", "title": "Fundraisers", "available": True,
        "desc": "Propose, track and report fundraiser campaigns.",
        "page": "pages/10_Fundraisers.py",
        "roles": None,
    },
    {
        "icon": "📅", "title": "Hall Calendar", "available": False,
        "desc": "Events, vacations and staff coverage schedule.",
        "page": None,
        "roles": ["master", "rlt_lead", "rlt_finan", "rlt_admin", "resident_fellow", "student"],
    },
    {
        "icon": "📊", "title": "Events & Budgets", "available": False,
        "desc": "Pre/post-event budgets and income tracking.",
        "page": None,
        "roles": None,
    },
    {
        "icon": "💸", "title": "Reimbursements", "available": False,
        "desc": "Submit expenses with receipts and track approvals.",
        "page": None,
        "roles": None,
    },
    {
        "icon": "📝", "title": "Sanction Alerts", "available": False,
        "desc": "ICF submissions and their approval status.",
        "page": None,
        "roles": ["master", "rlt_lead", "rlt_finan", "rlt_admin", "resident_fellow"],
    },
    {
        "icon": "⚙️", "title": "Admin", "available": True,
        "desc": "Users, roles, passwords and system settings.",
        "page": "pages/90_Admin.py",
        "roles": ["master"],
    },
]

visible = [m for m in MODULES if _can(m["roles"])]

if not visible:
    st.info("No modules available. Ask the Hall Master to assign you to a fundraiser.")
else:
    n_cols = 2
    for row_start in range(0, len(visible), n_cols):
        row = visible[row_start:row_start + n_cols]
        cols = st.columns(n_cols)
        for col, mod in zip(cols, row):
            with col:
                badge = ("<span class='sh-home-card-badge-soon'>soon</span>"
                         if not mod["available"] else "")
                st.markdown(
                    f'<div class="sh-home-card">'
                    f'<div class="sh-home-card-header">'
                    f'<span class="sh-home-card-icon">{mod["icon"]}</span>'
                    f'<span class="sh-home-card-title">{mod["title"]}</span>'
                    f'{badge}'
                    f'</div>'
                    f'<p class="sh-home-card-desc">{mod["desc"]}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if mod["available"] and mod["page"]:
                    st.markdown(
                        "<div style='height:0.3rem;'></div>",
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        f"Open {mod['title']}",
                        key=f"mod_{mod['title']}",
                        use_container_width=True,
                        type="primary",
                    ):
                        st.switch_page(mod["page"])
