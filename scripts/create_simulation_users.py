"""
Create the 9 simulation users for Sheares Hall testing.

Users created:
  - blka, blkb, blkc, blkd, blke (Resident Fellows, Blocks A-E)
  - jamie (RLT Finance), qiqi (RLT Lead), valli (RLT Admin)
  - guest1 (Student Ad-hoc, starts with scope=assigned_only on fundraiser/event)

All get password <username>123 and must_change_password=true.

Usage:   py scripts/create_simulation_users.py

Safe to re-run: skips users that already exist.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import toml
from supabase import create_client


USERS = [
    # username, full_name, role_code, user_category, assigned_block
    ("blka",   "Block A RF", "resident_fellow", "management", "A"),
    ("blkb",   "Block B RF", "resident_fellow", "management", "B"),
    ("blkc",   "Block C RF", "resident_fellow", "management", "C"),
    ("blkd",   "Block D RF", "resident_fellow", "management", "D"),
    ("blke",   "Block E RF", "resident_fellow", "management", "E"),
    ("jamie",  "Jamie",      "rlt_finan",       "management", None),
    ("qiqi",   "Qiqi",       "rlt_lead",        "management", None),
    ("valli",  "Valli",      "rlt_admin",       "management", None),
    ("guest1", "Guest 1",    "student_ad_hoc",  "ad_hoc",     None),
    ("dof",     "Student DOF", "student_dof",   "management", None),
]


def load_secrets() -> dict:
    path = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
    if not path.exists():
        print(f"ERROR: {path} not found.")
        sys.exit(1)
    return toml.load(path)


def default_scopes_for_role(role_code: str) -> list[tuple[str, str]]:
    """Return list of (module, scope_type) tuples for a given role."""
    if role_code in ("master", "rlt_lead", "rlt_finan", "rlt_admin",
                     "resident_fellow"):
        return [("calendar", "all"), ("fundraiser", "all"), ("event", "all"),
                ("reimbursement", "all"), ("sanction_alert", "all"),
                ("admin", "none")]
    if role_code == "student":
        return [("calendar", "all"), ("fundraiser", "assigned_only"),
                ("event", "assigned_only"),
                ("reimbursement", "own_only"),
                ("sanction_alert", "none"), ("admin", "none")]
    if role_code == "student_ad_hoc":
        return [("calendar", "none"), ("fundraiser", "assigned_only"),
                ("event", "assigned_only"),
                ("reimbursement", "own_only"),
                ("sanction_alert", "none"), ("admin", "none")]
    if role_code == "student_dof":
        return [("calendar", "none"), ("fundraiser", "all"),
                ("event", "none"),
                ("reimbursement", "none"),
                ("sanction_alert", "none"), ("admin", "none")]
    return []


def create_user(sb, u_tuple: tuple, domain: str, master_id: str | None) -> str:
    username, full_name, role_code, user_category, assigned_block = u_tuple
    password = f"{username}123"
    synthetic_email = f"{username}@{domain}"

    # Check if already exists (idempotent)
    existing = sb.table("users").select("id").eq("username", username).execute().data
    if existing:
        print(f"  [SKIP] {username} already exists")
        return existing[0]["id"]

    # Create auth user
    print(f"  [CREATE] {username} ({full_name})")
    auth_resp = sb.auth.admin.create_user({
        "email": synthetic_email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {"username": username, "full_name": full_name},
    })
    if not auth_resp or not auth_resp.user:
        print(f"    ERROR: auth creation failed for {username}")
        return None
    auth_id = auth_resp.user.id

    # Create public.users row
    user_row = sb.table("users").insert({
        "auth_user_id": auth_id,
        "username": username,
        "full_name": full_name,
        "user_category": user_category,
        "assigned_block": assigned_block,
        "is_active": True,
        "must_change_password": False,
        "created_by": master_id,
    }).execute().data[0]
    user_id = user_row["id"]

    # Assign role
    role_row = sb.table("roles").select("id").eq("code", role_code).execute().data
    if not role_row:
        print(f"    ERROR: role '{role_code}' not found")
        return user_id
    sb.table("user_roles").insert({
        "user_id": user_id,
        "role_id": role_row[0]["id"],
        "granted_by": master_id,
    }).execute()

    # Assign scopes
    for module, scope_type in default_scopes_for_role(role_code):
        sb.table("user_scopes").upsert({
            "user_id": user_id,
            "module": module,
            "scope_type": scope_type,
            "created_by": master_id,
        }, on_conflict="user_id,module").execute()

    # Track initial credentials (for admin panel display)
    sb.table("user_initial_credentials").upsert({
        "user_id": user_id,
        "initial_password_hint": f"{username}123",
        "created_by": master_id,
    }, on_conflict="user_id").execute()

    print(f"    OK — role={role_code}, block={assigned_block}, "
          f"temporary password={password}")
    return user_id


def main():
    secrets = load_secrets()
    sb = create_client(
        secrets["supabase"]["url"],
        secrets["supabase"]["service_role_key"],
    )
    domain = secrets["app"]["username_email_domain"]

    # Find the existing master (for audit trail)
    masters = sb.table("users").select("id").eq("username", "vrosa").execute().data
    master_id = masters[0]["id"] if masters else None

    print("=" * 60)
    print("CREATING SIMULATION USERS")
    print("=" * 60)
    print()

    for u in USERS:
        create_user(sb, u, domain, master_id)

    print()
    print("=" * 60)
    print("DONE. Summary of credentials:")
    print("=" * 60)
    for u in USERS:
        username = u[0]
        print(f"  username: {username:10s}   password: {username}123")
    print()
    print("All users are flagged must_change_password=true. On first login,")
    print("they will be prompted to change.")


if __name__ == "__main__":
    main()
