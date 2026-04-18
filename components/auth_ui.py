"""
Login screen and logged-in sidebar header.
"""
from __future__ import annotations

import streamlit as st

from services.auth_service import (
    login, logout, current_user, AuthError,
)


def render_login_screen() -> None:
    """Centered login form. Call when user is not authenticated."""
    st.markdown('<div class="sh-login-wrap">', unsafe_allow_html=True)
    st.markdown(
        '<div class="sh-login-title">Sheares Hall Ops</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sh-login-sub">Sign in with your hostel username</div>',
        unsafe_allow_html=True,
    )

    with st.form("sh_login_form", clear_on_submit=False):
        username = st.text_input("Username", key="sh_login_user",
                                 placeholder="e.g. vrosa")
        password = st.text_input("Password", type="password",
                                 key="sh_login_pw")
        submitted = st.form_submit_button("Sign in", type="primary",
                                          use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    if submitted:
        try:
            login(username, password)
            st.success("Signed in.")
            st.rerun()
        except AuthError as e:
            st.error(str(e))


def render_sidebar_user() -> None:
    """Sidebar header showing logged-in user + logout button."""
    u = current_user()
    if not u:
        return

    role_labels = {
        "master": "Hall Master",
        "rlt_lead": "RLT Lead",
        "rlt_finan": "RLT Finance",
        "rlt_admin": "RLT Admin",
        "resident_fellow": "Resident Fellow",
        "student": "Student",
        "student_ad_hoc": "Student (Ad-hoc)",
    }
    role_codes = u.get("roles") or []
    role_display = ", ".join(role_labels.get(r, r) for r in role_codes) or "No role"

    with st.sidebar:
        st.markdown(f"**{u['full_name']}**")
        st.caption(f"{role_display}")
        if u.get("assigned_block"):
            st.caption(f"Block {u['assigned_block']}")
        if st.button("Sign out", use_container_width=True, key="sh_logout_btn"):
            logout()
            st.rerun()
        st.divider()
