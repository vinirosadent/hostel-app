"""
Admin panel — Master only.

Lists all users with their roles, credential status, and controls for:
  - Reset password (generates temp password, shown once)
  - Deactivate / reactivate
  - Force password change on next login
"""
import pandas as pd
import streamlit as st

from components.ui import inject_theme, brand_stripe, status_badge
from components.auth_ui import render_sidebar_user
from services.auth_service import require_role, current_user
from services.admin_service import (
    list_all_users, reset_user_password,
    toggle_active, force_password_change,
)

st.set_page_config(page_title="Admin — Sheares Hall Ops",
                   page_icon="⚙️", layout="wide")
inject_theme()

require_role("master")
render_sidebar_user()

st.markdown("# Admin — Users")
brand_stripe()
st.caption("Manage user accounts, roles, and credentials.")

me = current_user()

# ---------- Load users ----------
users = list_all_users()

# ---------- Top summary ----------
total = len(users)
active_count = sum(1 for u in users if u["is_active"])
must_change = sum(1 for u in users if u["must_change_password"])

c1, c2, c3 = st.columns(3)
c1.metric("Total users", total)
c2.metric("Active", active_count)
c3.metric("Must change password", must_change)

st.divider()

# ---------- Newly reset password banner ----------
if "sh_last_reset" in st.session_state:
    info = st.session_state["sh_last_reset"]
    st.success(
        f"Temporary password generated for **{info['username']}**: "
        f"`{info['password']}`\n\n"
        "Share it with the user through a secure channel. "
        "It will not be shown again."
    )
    if st.button("Dismiss notice", type="secondary"):
        del st.session_state["sh_last_reset"]
        st.rerun()
    st.divider()

# ---------- Users table (read-only overview) ----------
st.subheader("All users")

rows = []
for u in users:
    cred = u.get("credentials") or {}
    rows.append({
        "Username":   u["username"],
        "Full name":  u["full_name"],
        "Role":       ", ".join(u.get("role_names") or []),
        "Block":      u.get("assigned_block") or "—",
        "Active":     "✓" if u["is_active"] else "✗",
        "Must change pw": "✓" if u["must_change_password"] else "",
        "Last login": u["last_login_at"][:10] if u.get("last_login_at") else "Never",
        "Pw changed": "✓" if cred.get("password_changed") else "—",
    })

df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True, hide_index=True)

st.divider()

# ---------- Per-user controls ----------
st.subheader("User actions")

user_options = {
    f"{u['username']} — {u['full_name']}": u
    for u in users if u["id"] != me["id"]  # Can't act on yourself
}
if not user_options:
    st.info("No other users available to manage.")
    st.stop()

selected_label = st.selectbox("Select a user", list(user_options.keys()))
selected = user_options[selected_label]

cA, cB, cC = st.columns(3)

with cA:
    if st.button("🔑 Reset password", use_container_width=True,
                 key="reset_btn", type="primary"):
        try:
            new_pw = reset_user_password(selected["id"], me["id"])
            st.session_state["sh_last_reset"] = {
                "username": selected["username"],
                "password": new_pw,
            }
            st.rerun()
        except Exception as e:
            st.error(f"Reset failed: {e}")
    st.caption("Generates a temporary password. User will be forced to change on next login.")

with cB:
    if selected["is_active"]:
        if st.button("🚫 Deactivate account", use_container_width=True,
                     key="deact_btn"):
            try:
                toggle_active(selected["id"], False)
                st.success(f"{selected['username']} deactivated.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
    else:
        if st.button("✓ Reactivate account", use_container_width=True,
                     key="reac_btn"):
            try:
                toggle_active(selected["id"], True)
                st.success(f"{selected['username']} reactivated.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
    st.caption("Deactivated users cannot log in.")

with cC:
    if not selected["must_change_password"]:
        if st.button("⚠ Force pw change", use_container_width=True,
                     key="force_btn"):
            try:
                force_password_change(selected["id"])
                st.success(f"{selected['username']} will be forced to change password on next login.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
    else:
        st.button("Already flagged", use_container_width=True,
                 disabled=True, key="force_btn_disabled")
    st.caption("Forces the user to set a new password on next login.")
