"""
Sheares Hall Ops — entry point (LIMS-style home).
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
role_display = " · ".join(
    role_label_map.get(r, r) for r in user_roles
) or "Member"

if user.get("must_change_password"):
    st.warning(
        "🔐 **Temporary password active.** Change it in the sidebar → Change Password."
    )

st.markdown(
    f"<h1 style='color:#0f172a;margin-bottom:0;'>"
    f"Welcome, {user_name} 👋</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    f"<p style='color:#64748b;font-size:1.05rem;margin-top:0.2rem;'>"
    f"{role_display} · Sheares Hall Ops Dashboard</p>",
    unsafe_allow_html=True,
)
st.markdown("---")


def _can(roles: list[str] | None) -> bool:
    return True if not roles else has_any_role(roles)


MODULES = [
    {
        "icon": "💰", "title": "Fundraisers",
        "desc": "Propose, track and report fundraiser campaigns.",
        "page": "pages/10_Fundraisers.py",
        "btn_label": "Open Fundraisers",
        "available": True, "primary": True, "roles": None,
    },
    {
        "icon": "📅", "title": "Hall Calendar",
        "desc": "Events, vacations and staff coverage schedule.",
        "page": None, "btn_label": "Coming soon",
        "available": False, "primary": False,
        "roles": ["master", "rlt_lead", "rlt_finan", "rlt_admin",
                  "resident_fellow", "student"],
    },
    {
        "icon": "📊", "title": "Events & Budgets",
        "desc": "Pre/post-event budgets and income tracking.",
        "page": None, "btn_label": "Coming soon",
        "available": False, "primary": False, "roles": None,
    },
    {
        "icon": "💸", "title": "Reimbursements",
        "desc": "Submit expenses with receipts and track approvals.",
        "page": None, "btn_label": "Coming soon",
        "available": False, "primary": False, "roles": None,
    },
    {
        "icon": "📝", "title": "Sanction Alerts",
        "desc": "ICF submissions and their approval status.",
        "page": None, "btn_label": "Coming soon",
        "available": False, "primary": False,
        "roles": ["master", "rlt_lead", "rlt_finan", "rlt_admin",
                  "resident_fellow"],
    },
    {
        "icon": "⚙️", "title": "Admin",
        "desc": "Users, roles, passwords and system settings.",
        "page": "pages/90_Admin.py",
        "btn_label": "Open Admin",
        "available": True, "primary": False,
        "roles": ["master"],
    },
]

visible = [m for m in MODULES if _can(m["roles"])]

if not visible:
    st.info(
        "No modules available. Ask the Hall Master to assign you to a fundraiser."
    )
else:
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    cols = [c1, c2, c3]

    for i, mod in enumerate(visible):
        with cols[i % 3]:
            with st.container(border=True):
                badge = ""
                if not mod["available"]:
                    badge = (
                        " <span style='font-size:0.62rem;color:#94a3b8;"
                        "background:#f1f5f9;padding:2px 8px;border-radius:10px;"
                        "vertical-align:middle;margin-left:0.3rem;'>soon</span>"
                    )

                st.markdown(
                    f"<h4 style='color:#0f172a;margin-top:0;margin-bottom:0.4rem;'>"
                    f"{mod['icon']} {mod['title']}{badge}</h4>"
                    f"<p style='color:#475569;font-size:0.95rem;height:45px;"
                    f"margin:0 0 0.5rem 0;line-height:1.4;'>"
                    f"{mod['desc']}</p>",
                    unsafe_allow_html=True,
                )

                if mod["available"] and mod["page"]:
                    btn_type = "primary" if mod["primary"] else "secondary"
                    if st.button(
                        mod["btn_label"],
                        key=f"mod_{mod['title']}",
                        use_container_width=True,
                        type=btn_type,
                    ):
                        st.switch_page(mod["page"])
                else:
                    st.button(
                        mod["btn_label"],
                        key=f"mod_{mod['title']}",
                        use_container_width=True,
                        disabled=True,
                    )
