"""
Change password page. Any authenticated user can change their own password.
Appears at the bottom of the sidebar nav because of the "99_" filename prefix.
"""
import streamlit as st

from components.ui import inject_theme
from components.auth_ui import render_sidebar_user
from services.auth_service import (
    require_login, change_own_password, AuthError,
)

st.set_page_config(page_title="Change Password — Sheares Hall Ops",
                   page_icon="🔒", layout="centered")
inject_theme()

user = require_login()
render_sidebar_user()

st.markdown("# Change Password")
st.caption(f"Logged in as **{user['full_name']}** (`{user['username']}`)")

if user.get("must_change_password"):
    st.warning(
        "You are using a temporary password. Choose a new one below before "
        "continuing to the rest of the app."
    )

st.write("")

with st.form("sh_change_pw_form", clear_on_submit=True):
    new1 = st.text_input("New password", type="password",
                         help="Minimum 12 characters.")
    new2 = st.text_input("Confirm new password", type="password")
    submitted = st.form_submit_button("Update password", type="primary")

if submitted:
    if new1 != new2:
        st.error("The two passwords do not match.")
    elif len(new1) < 12:
        st.error("Password must be at least 12 characters.")
    else:
        try:
            change_own_password(new1)
            st.success("Password updated. You may continue using the app.")
            st.rerun()
        except AuthError as e:
            st.error(str(e))

st.divider()
st.caption(
    "If you forget your password, contact the Hall Master to reset it. "
    "The system does not send emails."
)
