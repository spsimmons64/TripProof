-- ################################################################################################
-- # 007 - account status: active | inactive | setup.
-- #
-- #   setup     assigned by the system to accounts that signed up online and haven't completed their
-- #             application. Staff never choose it. Its users can sign in, to finish the application.
-- #   active    normal.
-- #   inactive  switched off: every user is signed out, sign-in and invitation links are refused.
-- #             (Previously called "suspended".)
-- ################################################################################################
UPDATE accounts SET status = 'inactive' WHERE status = 'suspended';

ALTER TABLE accounts
    ADD CONSTRAINT IF NOT EXISTS ck_accounts_status CHECK (status IN ('active', 'inactive', 'setup'));
