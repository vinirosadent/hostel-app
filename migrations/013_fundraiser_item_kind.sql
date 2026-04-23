-- Migration 013: Distinguish sale items from other costs
-- Run in Supabase SQL Editor

-- Add an item_kind column so the fundraiser_items table can carry both:
--   'sale'       → products that are sold (enter into selling options)
--   'other_cost' → non-sold expenses such as delivery, design, printing.
--                  These do not appear in selling options or stock
--                  reconciliation, but they are still subtracted from
--                  Gross Revenue when computing Gross Profit.

ALTER TABLE fundraiser_items
    ADD COLUMN IF NOT EXISTS item_kind text NOT NULL DEFAULT 'sale';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'fundraiser_items'
          AND constraint_name = 'fundraiser_items_item_kind_check'
    ) THEN
        ALTER TABLE fundraiser_items
            ADD CONSTRAINT fundraiser_items_item_kind_check
            CHECK (item_kind IN ('sale', 'other_cost'));
    END IF;
END $$;
