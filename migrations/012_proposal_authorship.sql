ALTER TABLE fundraisers
    ADD COLUMN IF NOT EXISTS proposal_prepared_by text,
    ADD COLUMN IF NOT EXISTS on_behalf_of text;

COMMENT ON COLUMN fundraisers.proposal_prepared_by
    IS 'Full name of the student who drafted this proposal';
COMMENT ON COLUMN fundraisers.on_behalf_of
    IS 'Name of the committee or activity that this fundraiser represents';
