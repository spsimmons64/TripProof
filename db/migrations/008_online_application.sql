-- ################################################################################################
-- # 008 - the online application (/apply): billing references and Terms of Service acceptance.
-- #
-- # An application creates the account in 'setup' at step 1. Step 2 verifies a card with a Stripe
-- # SetupIntent (no customer yet). Step 3 records acceptance of the Terms, creates the Stripe
-- # customer, attaches the verified card and makes the account active.
-- #
-- # Card data never touches TripProof: only Stripe ids and the brand / last 4 / expiry shown back to
-- # the customer are stored. The TOS acceptance keeps the version, a SHA-256 of the exact text shown,
-- # who accepted, when and from where - enough to prove what was agreed to.
-- ################################################################################################
ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS signupsource          VARCHAR(8)   NOT NULL DEFAULT 'admin' AFTER status,  -- admin | online
    ADD COLUMN IF NOT EXISTS stripecustomerid      VARCHAR(64)  NULL,
    ADD COLUMN IF NOT EXISTS stripesetupintentid   VARCHAR(64)  NULL,
    ADD COLUMN IF NOT EXISTS stripepaymentmethodid VARCHAR(64)  NULL,
    ADD COLUMN IF NOT EXISTS cardbrand             VARCHAR(20)  NULL,
    ADD COLUMN IF NOT EXISTS cardlast4             CHAR(4)      NULL,
    ADD COLUMN IF NOT EXISTS cardexp               VARCHAR(7)   NULL,       -- MM/YYYY
    ADD COLUMN IF NOT EXISTS cardverifiedon        DATETIME     NULL,
    ADD COLUMN IF NOT EXISTS tosversion            VARCHAR(20)  NULL,
    ADD COLUMN IF NOT EXISTS tossha256             CHAR(64)     NULL,
    ADD COLUMN IF NOT EXISTS tosacceptedon         DATETIME     NULL,
    ADD COLUMN IF NOT EXISTS tosacceptedby         VARCHAR(36)  NULL,
    ADD COLUMN IF NOT EXISTS tosacceptedip         VARCHAR(45)  NULL,
    ADD COLUMN IF NOT EXISTS applicationcompletedon DATETIME    NULL;

ALTER TABLE accounts ADD UNIQUE KEY IF NOT EXISTS ux_accounts_stripecustomer (stripecustomerid);
