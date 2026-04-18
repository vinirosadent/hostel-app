"""
Sheares Hall Ops — entry point.

Shows the login screen when the user is not authenticated, and a simple
home/dashboard once logged in. Module pages live in pages/.
"""
import streamlit as st

from services.auth_service import current_user, is_authenticated
from components.ui import inject_theme, brand_stripe, kpi
from components.auth_ui import render_login_screen, render_sidebar_user

st.set_page_config(
    page_title="Sheares Hall Ops",
    page_icon="🟠",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_theme()


if not is_authenticated():
    render_login_screen()
    st.stop()


# Authenticated — show home
render_sidebar_user()

u = current_user()

st.markdown(f"# Welcome, {u['full_name']}")
brand_stripe()

if u.get("must_change_password"):
    st.warning(
        "You are using a temporary password. Please open "
        "**Change Password** from the sidebar and update it now."
    )

st.caption(
    "This is the home screen. Module pages (Fundraisers, Events, Calendar, "
    "Reimbursements, Admin) will appear in the sidebar as we build them."
)

c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown(kpi("0", "Active fundraisers"), unsafe_allow_html=True)
with c2: st.markdown(
    kpi("0", "Pending approvals", variant="accent"),
    unsafe_allow_html=True,
)
with c3: st.markdown(
    kpi("—", "Your last login", variant="success"),
    unsafe_allow_html=True,
)
with c4: st.markdown(
    kpi("—", "Outstanding reports", variant="warning"),
    unsafe_allow_html=True,
)

st.write("")
st.info(
    "Next development step: admin panel to create simulation users, "
    "then the Fundraiser module."
)
