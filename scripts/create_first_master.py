"""
Bootstrap script: creates the first Hall Master user.

Run once, after migrations are applied, before using the app.
Usage:  py scripts/create_first_master.py
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import toml
from supabase import create_client


def load_secrets() -> dict:
    path = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
    if not path.exists():
        print(f"ERROR: {path} not found. Create it first.")
        sys.exit(1)
    return toml.load(path)


def main() -> None:
    secrets = load_secrets()
    url = secrets["supabase"]["url"]
    service_key = secrets["supabase"]["service_role_key"]
    domain = secrets["app"]["username_email_domain"]

    print("=" * 60)
    print("BOOTSTRAP: Create first Hall Master")
    print("=" * 60)
    print()

    sb = create_client(url, service_key)

    existing = sb.table("users").select("id, username").execute().data or []
    if existing:
        print(f"WARNING: {len(existing)} user(s) already exist:")
        for u in existing[:5]:
            print(f"  - {u['username']}")
        confirm = input("\nProceed anyway and create another master? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            sys.exit(0)

    username = input("Username (letters/numbers/dash/underscore, 3-32 chars): ").strip().lower()
    if len(username) < 3 or len(username) > 32:
        print("ERROR: username must be 3-32 chars.")
        sys.exit(1)

    full_name = input("Full name: ").strip()
    if not full_name:
        print("ERROR: full name is required.")
        sys.exit(1)

    while True:
        pw1 = getpass.getpass("Password (min 12 chars): ")
        if len(pw1) < 12:
            print("ERROR: password must be at least 12 chars.")
            continue
        pw2 = getpass.getpass("Confirm password: ")
        if pw1 != pw2:
            print("ERROR: passwords don't match.")
            continue
        break

    synthetic_email = f"{username}@{domain}"
    print()
    print(f"Creating Supabase auth user: {synthetic_email}")
    auth_resp = sb.auth.admin.create_user({
        "email": synthetic_email,
        "password": pw1,
        "email_confirm": True,
        "user_metadata": {"username": username, "full_name": full_name},
    })
    auth_user = auth_resp.user
    if not auth_user:
        print("ERROR: auth user creation failed.")
        sys.exit(1)
    print(f"  auth.users.id = {auth_user.id}")

    print("Creating public.users row...")
    user_row = sb.table("users").insert({
        "auth_user_id": auth_user.id,
        "username": username,
        "full_name": full_name,
        "user_category": "management",
        "is_active": True,
        "must_change_password": False,
    }).execute().data[0]
    print(f"  public.users.id = {user_row['id']}")

    print("Assigning 'master' role...")
    master_role = sb.table("roles").select("id").eq("code", "master").execute().data[0]
    sb.table("user_roles").insert({
        "user_id": user_row["id"],
        "role_id": master_role["id"],
    }).execute()

    print("Granting full scopes...")
    for module in ["calendar", "fundraiser", "event",
                   "reimbursement", "sanction_alert", "admin"]:
        sb.table("user_scopes").upsert({
            "user_id": user_row["id"],
            "module": module,
            "scope_type": "all",
        }, on_conflict="user_id,module").execute()

    print()
    print("=" * 60)
    print("SUCCESS! You can now log in with:")
    print(f"  Username: {username}")
    print(f"  Password: (the one you just set)")
    print("=" * 60)


if __name__ == "__main__":
    main()
