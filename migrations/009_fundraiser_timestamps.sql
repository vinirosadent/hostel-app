-- Migration 009: Add workflow timestamps to fundraisers
-- Run in Supabase SQL Editor

ALTER TABLE fundraisers
    ADD COLUMN IF NOT EXISTS submitted_at      timestamptz,
    ADD COLUMN IF NOT EXISTS rf_approved_at    timestamptz,
    ADD COLUMN IF NOT EXISTS master_approved_at timestamptz;

-- Note: master_review is a new status string value.
-- No enum change needed — status is a text column.
-- Allowed flow: draft → rf_review → master_review → approved
-- (master_review means RF approved, awaiting Master final approval)
