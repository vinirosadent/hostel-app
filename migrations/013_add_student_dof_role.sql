-- 013_add_student_dof_role.sql
-- Adds the 'student_dof' role used by Aba 6 (Report Confirmations) as the
-- second signer in the closure sequence.

INSERT INTO roles (code, name, description)
VALUES (
    'student_dof',
    'Student DOF',
    'Student oversight of fundraisers and events; second closure signer'
)
ON CONFLICT (code) DO NOTHING;
