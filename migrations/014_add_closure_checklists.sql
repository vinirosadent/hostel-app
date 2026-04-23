-- 014_add_closure_checklists.sql
-- Adiciona 3 colunas JSONB na tabela fundraisers, uma para cada novo
-- signatário da Aba 6 (DOF, Finance, Master). A coluna rf_checklist
-- já existia de antes, não é mexida aqui.

ALTER TABLE fundraisers
    ADD COLUMN IF NOT EXISTS dof_checklist     JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS finance_checklist JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS master_checklist  JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN fundraisers.dof_checklist     IS 'Checklist de fechamento do DOF (Aba 6).';
COMMENT ON COLUMN fundraisers.finance_checklist IS 'Checklist de fechamento do Finance (Aba 6).';
COMMENT ON COLUMN fundraisers.master_checklist  IS 'Checklist de fechamento final do Master (Aba 6).';
