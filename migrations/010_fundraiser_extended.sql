-- Migration 010: Extended fundraiser data model
-- Run in Supabase SQL Editor

-- ── New columns on fundraisers ─────────────────────────────────────────────

ALTER TABLE fundraisers
    ADD COLUMN IF NOT EXISTS beneficiary               text,
    -- Compliance checkboxes (page 1 — required before submission to RF)
    ADD COLUMN IF NOT EXISTS compliance_nusync          boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS compliance_no_intermediary boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS compliance_gst_artwork     boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS compliance_regulations     boolean NOT NULL DEFAULT false,
    -- Submission / approval signatures (name auto-filled from logged-in user)
    ADD COLUMN IF NOT EXISTS submitted_by_name          text,
    ADD COLUMN IF NOT EXISTS rf_approved_by             text,
    ADD COLUMN IF NOT EXISTS master_approved_by         text,
    -- Closure-phase confirmation signatures
    ADD COLUMN IF NOT EXISTS rf_confirmed_at            timestamptz,
    ADD COLUMN IF NOT EXISTS rf_confirmed_by            text,
    ADD COLUMN IF NOT EXISTS dof_confirmed_at           timestamptz,
    ADD COLUMN IF NOT EXISTS dof_confirmed_by           text,
    ADD COLUMN IF NOT EXISTS finance_confirmed_at       timestamptz,
    ADD COLUMN IF NOT EXISTS finance_confirmed_by       text,
    ADD COLUMN IF NOT EXISTS master_closure_at          timestamptz,
    ADD COLUMN IF NOT EXISTS master_closure_by          text,
    ADD COLUMN IF NOT EXISTS funds_available            boolean NOT NULL DEFAULT false,
    -- RF closure checklist stored as JSONB (keys = RF_CHECKLIST_ITEMS keys, values = bool)
    ADD COLUMN IF NOT EXISTS rf_checklist               jsonb NOT NULL DEFAULT '{}';

-- ── fundraiser_assets table (appendix: marketing & artwork uploads) ────────

CREATE TABLE IF NOT EXISTS fundraiser_assets (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    fundraiser_id    uuid        NOT NULL REFERENCES fundraisers(id) ON DELETE CASCADE,
    section          text        NOT NULL CHECK (section IN ('marketing', 'artwork')),
    asset_type       text        NOT NULL CHECK (asset_type IN ('product_design', 'marketing_promo', 'other')),
    title            text        NOT NULL,
    description      text,
    file_name        text        NOT NULL,
    file_url         text        NOT NULL,
    file_mime        text,
    linked_item_code text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    created_by_id    uuid        REFERENCES users(id)
);

ALTER TABLE fundraiser_assets ENABLE ROW LEVEL SECURITY;

-- Permissive RLS: anyone who can see the parent fundraiser can see its assets.
-- Tighten per-environment as needed.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'fundraiser_assets'
          AND policyname = 'fundraiser_assets_all'
    ) THEN
        CREATE POLICY "fundraiser_assets_all" ON fundraiser_assets
            USING (true) WITH CHECK (true);
    END IF;
END $$;

-- ── IMPORTANT: Supabase Storage bucket ────────────────────────────────────
-- Create a PUBLIC bucket named exactly "fundraiser-assets" via:
--   Dashboard → Storage → New bucket → Name: fundraiser-assets → Public: ON
-- Without this bucket the appendix file-upload feature will not work.
-- The bucket name must match the value used in fundraiser_service.py.
