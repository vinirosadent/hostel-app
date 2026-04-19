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
    """Sidebar header showing logged-in user + custom navigation + logout."""
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
    role_display = " · ".join(role_labels.get(r, r) for r in role_codes) or "No role"

    with st.sidebar:
        # User info block
        st.markdown(
            f"<div style='padding:0.5rem 0;'>"
            f"<div style='font-weight:600;color:#0f172a;font-size:0.95rem;'>{u['full_name']}</div>"
            f"<div style='color:#64748b;font-size:0.8rem;'>{role_display}</div>"
            + (f"<div style='color:#94a3b8;font-size:0.78rem;'>Block {u['assigned_block']}</div>" if u.get("assigned_block") else "")
            + "</div>",
            unsafe_allow_html=True,
        )

        # Navigation links
        st.markdown("---")
        st.markdown(
            "<div style='font-size:0.75rem;font-weight:600;color:#94a3b8;"
            "text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.4rem;'>"
            "Navigation</div>",
            unsafe_allow_html=True,
        )
        if st.button("🏠  Home", use_container_width=True, key="nav_home"):
            st.switch_page("app.py")
        if st.button("💰  Fundraisers", use_container_width=True, key="nav_fundraisers"):
            st.switch_page("pages/10_Fundraisers.py")

        from services.auth_service import has_any_role
        if has_any_role(["master"]):
            if st.button("⚙️  Admin", use_container_width=True, key="nav_admin"):
                st.switch_page("pages/90_Admin.py")

        st.markdown("---")
        if st.button("🔒  Change Password", use_container_width=True, key="nav_pw"):
            st.switch_page("pages/99_Change_Password.py")
        if st.button("↩  Sign out", use_container_width=True, key="sh_logout_btn"):
            logout()
            st.rerun()
