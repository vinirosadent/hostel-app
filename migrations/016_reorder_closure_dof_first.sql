-- 016_reorder_closure_dof_first.sql
-- Reforma do closure workflow: DOF assina antes do RF.
-- Também corrige dívida técnica pré-existente: CHECK constraint aceitava
-- apenas 7 status quando o código Python usava 11.
-- Status removido: dof_confirming
-- Status novo: rf_confirming
-- Status que faltavam: master_review, finance_confirming, master_confirming
-- Colunas: NENHUMA renomeação — o que muda é a ordem em que são carimbadas.

ALTER TABLE fundraisers
    DROP CONSTRAINT IF EXISTS fundraisers_status_check;

ALTER TABLE fundraisers
    ADD CONSTRAINT fundraisers_status_check
    CHECK (status = ANY (ARRAY[
        'draft'::text,
        'rf_review'::text,
        'master_review'::text,
        'approved'::text,
        'executing'::text,
        'reporting'::text,
        'rf_confirming'::text,
        'finance_confirming'::text,
        'master_confirming'::text,
        'closed'::text,
        'rejected'::text
    ]));

UPDATE fundraisers
   SET status = 'rf_confirming'
 WHERE status = 'dof_confirming';
