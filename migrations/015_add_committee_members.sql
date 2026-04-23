-- 015_add_committee_members.sql
-- Tabela para registro documental de membros do comitê do fundraiser,
-- em texto livre. NÃO tem FK para users — pode listar voluntários
-- externos que não têm login no app. Permissão de edição do fundraiser
-- continua sendo controlada por fundraiser_students.
-- RLS: usa o helper can_see_fundraiser() já existente no banco.

CREATE TABLE IF NOT EXISTS fundraiser_committee_members (
    id             UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    fundraiser_id  UUID       NOT NULL
                              REFERENCES fundraisers(id)
                              ON DELETE CASCADE,
    member_name    TEXT       NOT NULL,
    position       TEXT       NOT NULL DEFAULT '',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_id  UUID       REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS fundraiser_committee_members_fundraiser_idx
    ON fundraiser_committee_members(fundraiser_id);

ALTER TABLE fundraiser_committee_members ENABLE ROW LEVEL SECURITY;

CREATE POLICY fcm_all ON fundraiser_committee_members
    FOR ALL
    USING (can_see_fundraiser(fundraiser_id))
    WITH CHECK (can_see_fundraiser(fundraiser_id));
