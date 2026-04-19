"""
Create sample fundraisers in various states for visual testing.

Creates 4 fundraisers owned by guest1:
  1. DRAFT          — just started, minimal info
  2. RF_REVIEW      — submitted, awaiting RF approval
  3. APPROVED       — approved by RF+Master, ready to execute
  4. EXECUTING      — running, some items/options defined

Also adds sample items and selling options to some of them.

Usage:   py scripts/seed_sample_fundraisers.py

Safe to re-run: skips fundraisers that already exist by name.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import toml
from supabase import create_client


def load_secrets() -> dict:
    path = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
    return toml.load(path)


def main():
    secrets = load_secrets()
    sb = create_client(
        secrets["supabase"]["url"],
        secrets["supabase"]["service_role_key"],
    )

    # Resolve user IDs
    guest1 = sb.table("users").select("id").eq("username", "guest1").execute().data
    blka = sb.table("users").select("id").eq("username", "blka").execute().data
    if not guest1 or not blka:
        print("ERROR: Need guest1 and blka users to exist first.")
        print("Run create_simulation_users.py first.")
        sys.exit(1)
    guest1_id = guest1[0]["id"]
    blka_id = blka[0]["id"]

    fundraisers = [
        {
            "name": "Pineapple Tart Christmas Drive",
            "objective": "Raise funds for the block welfare through festive sales.",
            "status": "draft",
            "items": [],
            "options": [],
        },
        {
            "name": "Valentine's Rose Bouquets",
            "objective": "Sell rose bouquets and chocolates for Valentine's Day fundraiser.",
            "status": "rf_review",
            "items": [
                ("A", "Flowers Co", 100, 3.00),
                ("B", "Sweet Co",   80, 4.00),
            ],
            "options": [
                ("Single A", "single", {"A": 1}, 10.00),
                ("Single B", "single", {"B": 1}, 6.00),
                ("Bundle",   "bundle", {"A": 1, "B": 1}, 14.00),
            ],
        },
        {
            "name": "Sheares Orientation Hoodies",
            "objective": "Custom hoodies for new freshmen. Proceeds support orientation activities.",
            "status": "approved",
            "items": [
                ("A", "PrintHub", 150, 7.20),
            ],
            "options": [
                ("Hoodie Standard", "single", {"A": 1}, 15.00),
            ],
        },
        {
            "name": "Hall Movie Night Popcorn",
            "objective": "Popcorn and snacks sold during monthly hall movie screenings.",
            "status": "executing",
            "items": [
                ("A", "Snack Depot", 200, 1.50),
                ("B", "Snack Depot", 200, 2.00),
            ],
            "options": [
                ("Popcorn Small", "single", {"A": 1}, 3.00),
                ("Popcorn+Drink", "bundle", {"A": 1, "B": 1}, 5.00),
            ],
        },
    ]

    for spec in fundraisers:
        existing = sb.table("fundraisers").select("id").eq(
            "name", spec["name"]
        ).execute().data
        if existing:
            print(f"  [SKIP] {spec['name']} already exists")
            continue

        # Must insert as draft first (RLS would block other statuses on insert
        # from a non-staff user, but we're using service_role so it's fine).
        fr = sb.table("fundraisers").insert({
            "name":            spec["name"],
            "objective":       spec["objective"],
            "status":          "draft",
            "created_by_id":   guest1_id,
            "rf_in_charge_id": blka_id,
        }).execute().data[0]
        fr_id = fr["id"]
        print(f"  [CREATE] {spec['name']} (status will be {spec['status']})")

        # Register guest1 as chair
        sb.table("fundraiser_students").upsert({
            "fundraiser_id": fr_id,
            "user_id":       guest1_id,
            "position":      "chair",
            "added_by":      guest1_id,
        }, on_conflict="fundraiser_id,user_id").execute()

        # Add items
        for code, supplier, qty, cost in spec["items"]:
            sb.table("fundraiser_items").upsert({
                "fundraiser_id": fr_id,
                "item_code":     code,
                "supplier":      supplier,
                "quantity":      qty,
                "unit_cost":     cost,
                "requires_quote": (qty * cost) >= 1000,
            }, on_conflict="fundraiser_id,item_code").execute()

        # Add selling options
        items_map = {
            it["item_code"]: float(it["unit_cost"])
            for it in sb.table("fundraiser_items").select(
                "item_code, unit_cost"
            ).eq("fundraiser_id", fr_id).execute().data or []
        }
        for name, opt_type, comp, price in spec["options"]:
            unit_cost = sum(items_map.get(c, 0) * q for c, q in comp.items())
            margin = (price - unit_cost) / price if price > 0 else 0
            sb.table("fundraiser_selling_options").upsert({
                "fundraiser_id": fr_id,
                "option_name":   name,
                "option_type":   opt_type,
                "composition":   comp,
                "unit_cost":     unit_cost,
                "selling_price": price,
                "is_acceptable": margin >= 0.30,
            }, on_conflict="fundraiser_id,option_name").execute()

        # Now set the desired final status
        if spec["status"] != "draft":
            sb.table("fundraisers").update(
                {"status": spec["status"]}
            ).eq("id", fr_id).execute()

        print(f"    OK — {len(spec['items'])} items, {len(spec['options'])} options")

    print()
    print("Done. Log in as guest1 to see the 4 sample fundraisers.")
    print("Log in as blka to see one waiting in RF review.")
    print("Log in as vrosa to see all of them.")


if __name__ == "__main__":
    main()
