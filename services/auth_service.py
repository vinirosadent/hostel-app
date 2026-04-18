"""
Authentication service.

Wraps Supabase Auth with a username-based login layer. Supabase requires an
email, so we synthesize one per-user using the configured domain. The user
only ever sees the username.

Session state keys managed here:
  - sh_user: dict snapshot of the logged-in user
  - sh_auth_session: Supabase auth session object

Call `require_login()` at the top of every page that needs auth.
"""
from __future__ import annotations

import streamlit as st

from services.supabase_client import get_supabase, get_username_email


class AuthError(Exception):
    """Raised for login/password errors shown to the user."""


# ------------------------------------------------------------
# Session helpers
# ------------------------------------------------------------

def current_user() -> dict | None:
    return st.session_state.get("sh_user")


def is_authenticated() -> bool:
    return current_user() is not None


def has_role(role_code: str) -> bool:
    u = current_user()
    if not u:
        return False
    return role_code in (u.get("roles") or [])


def has_any_role(role_codes: list[str]) -> bool:
    u = current_user()
    if not u:
        return False
    user_roles = set(u.get("roles") or [])
    return bool(user_roles.intersection(role_codes))


def is_staff() -> bool:
    return has_any_role(["master", "rlt_lead", "rlt_finan",
                         "rlt_admin", "resident_fellow"])


def is_master() -> bool:
    return has_role("master")


# ------------------------------------------------------------
# Login / Logout
# ------------------------------------------------------------

def login(username: str, password: str) -> dict:
    """Authenticate with Supabase Auth and hydrate the session."""
    username_clean = (username or "").strip().lower()
    if not username_clean:
        raise AuthError("Username is required.")
    if not password:
        raise AuthError("Password is required.")

    synthetic_email = get_username_email(username_clean)
    sb = get_supabase()

    try:
        auth_resp = sb.auth.sign_in_with_password({
            "email": synthetic_email,
            "password": password,
        })
    except Exception as e:
        msg = str(e).lower()
        if "invalid" in msg or "credentials" in msg:
            raise AuthError("Invalid username or password.") from e
        raise AuthError(f"Login failed: {e}") from e

    if not auth_resp or not auth_resp.user:
        raise AuthError("Invalid username or password.")

    profile = _load_profile(auth_resp.user.id)
    if not profile:
        raise AuthError("Your account is not fully provisioned. Contact admin.")
    if not profile.get("is_active", False):
        raise AuthError("This account is deactivated.")

    st.session_state["sh_user"] = profile
    st.session_state["sh_auth_session"] = auth_resp.session

    try:
        sb.table("users").update(
            {"last_login_at": "now()"}
        ).eq("id", profile["id"]).execute()
    except Exception:
        pass

    return profile


def logout() -> None:
    try:
        sb = get_supabase()
        sb.auth.sign_out()
    except Exception:
        pass
    for key in ("sh_user", "sh_auth_session"):
        st.session_state.pop(key, None)


# ------------------------------------------------------------
# Password management
# ------------------------------------------------------------

def change_own_password(new_password: str) -> None:
    if not is_authenticated():
        raise AuthError("You must be logged in to change your password.")
    if len(new_password) < 12:
        raise AuthError("Password must be at least 12 characters.")
    sb = get_supabase()
    try:
        sb.auth.update_user({"password": new_password})
    except Exception as e:
        raise AuthError(f"Could not update password: {e}") from e

    user = current_user() or {}
    if user.get("must_change_password"):
        try:
            sb.table("users").update(
                {"must_change_password": False}
            ).eq("id", user["id"]).execute()
            user["must_change_password"] = False
            st.session_state["sh_user"] = user
        except Exception:
            pass


# ------------------------------------------------------------
# Gates
# ------------------------------------------------------------

def require_login() -> dict:
    """Call at the top of every protected page."""
    u = current_user()
    if u is None:
        st.warning("Please log in to continue.")
        st.info("Go back to the main app page to sign in.")
        st.stop()
    if u.get("must_change_password"):
        current_page = st.session_state.get("_sh_current_page", "")
        if "change_password" not in current_page.lower():
            st.warning(
                "You must change your password before continuing. "
                "Open **Change Password** from the sidebar."
            )
            st.stop()
    return u


def require_role(*role_codes: str) -> dict:
    u = require_login()
    if not has_any_role(list(role_codes)):
        st.error("You don't have permission to view this page.")
        st.stop()
    return u


# ------------------------------------------------------------
# Internals
# ------------------------------------------------------------

def _load_profile(auth_user_id: str) -> dict | None:
    sb = get_supabase()

    users_res = sb.table("users").select(
        "id, username, full_name, user_category, assigned_block, "
        "is_active, must_change_password, auth_user_id"
    ).eq("auth_user_id", auth_user_id).execute()
    if not users_res.data:
        return None
    user = users_res.data[0]

    roles_res = sb.table("user_roles").select(
        "role_id, roles(code)"
    ).eq("user_id", user["id"]).execute()
    role_codes = [r["roles"]["code"] for r in (roles_res.data or [])
                  if r.get("roles")]

    scopes_res = sb.table("user_scopes").select(
        "module, scope_type, target_ids"
    ).eq("user_id", user["id"]).execute()
    scopes = {s["module"]: {"scope_type": s["scope_type"],
                            "target_ids": s.get("target_ids") or []}
              for s in (scopes_res.data or [])}

    return {**user, "roles": role_codes, "scopes": scopes}
