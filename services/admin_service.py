"""
Admin service — user management for Master only.

Uses the service_role client (bypasses RLS) because admin operations need
to write to auth.users, which RLS cannot protect directly.
"""
from __future__ import annotations

import secrets
import string
from typing import Any

from services.supabase_client import get_supabase_admin


def generate_temp_password(length: int = 14) -> str:
    """Generate a readable temporary password using letters and digits."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def list_all_users() -> list[dict]:
    """Fetch all users with their roles and credential status."""
    sb = get_supabase_admin()
    users = sb.table("users").select(
        "id, username, full_name, user_category, assigned_block, "
        "is_active, must_change_password, last_login_at, created_at"
    ).order("username").execute().data or []

    # Attach roles
    for u in users:
        roles_res = sb.table("user_roles").select(
            "roles(code, name)"
        ).eq("user_id", u["id"]).execute().data or []
        u["roles"] = [r["roles"]["code"] for r in roles_res if r.get("roles")]
        u["role_names"] = [r["roles"]["name"] for r in roles_res if r.get("roles")]

    # Attach credential info
    creds = sb.table("user_initial_credentials").select(
        "user_id, initial_password_hint, password_changed, "
        "password_changed_at, last_reset_at"
    ).execute().data or []
    creds_by_user = {c["user_id"]: c for c in creds}
    for u in users:
        u["credentials"] = creds_by_user.get(u["id"])

    return users


def reset_user_password(user_id: str, reset_by_id: str) -> str:
    """Generate a new temporary password, apply it via service_role,
    flip must_change_password=true, and record the reset.
    Returns the new temporary password (shown once to admin)."""
    sb = get_supabase_admin()

    user = sb.table("users").select("auth_user_id, username").eq(
        "id", user_id
    ).execute().data
    if not user:
        raise ValueError("User not found.")
    auth_id = user[0]["auth_user_id"]

    new_password = generate_temp_password()
    sb.auth.admin.update_user_by_id(auth_id, {"password": new_password})

    sb.table("users").update({
        "must_change_password": True,
    }).eq("id", user_id).execute()

    sb.table("user_initial_credentials").upsert({
        "user_id": user_id,
        "initial_password_hint": "reset",
        "password_changed": False,
        "last_reset_at": "now()",
        "last_reset_by": reset_by_id,
    }, on_conflict="user_id").execute()

    return new_password


def toggle_active(user_id: str, active: bool) -> None:
    sb = get_supabase_admin()
    sb.table("users").update({"is_active": active}).eq("id", user_id).execute()


def force_password_change(user_id: str) -> None:
    """Flag user to be forced to change password on next login."""
    sb = get_supabase_admin()
    sb.table("users").update(
        {"must_change_password": True}
    ).eq("id", user_id).execute()
