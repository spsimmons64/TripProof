-- ################################################################################################
-- # 009 - subscription plans priced by fleet size, and customers' subscriptions.
-- #
-- # plans: one row per fleet-size tier. A customer's plan follows from their vehicle count - the
-- # active tier whose [minvehicles, maxvehicles] range contains it (maxvehicles NULL = no upper
-- # limit). monthlyprice NULL means "contact us": shown, but not offered online.
-- #
-- # Stripe prices are immutable, so a plan remembers the Stripe price it last created and the
-- # amount it was created for; when the admin changes the price a new Stripe price is made on next
-- # use, and existing subscribers keep the one they signed up at.
-- #
-- # subscriptions: a customer's subscription, with the price and fleet size snapshotted at signup.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS plans (
    recordid          VARCHAR(36)   NOT NULL,
    code              VARCHAR(32)   NOT NULL,
    name              VARCHAR(64)   NOT NULL,
    description       VARCHAR(255)  NULL,
    minvehicles       INT           NOT NULL,
    maxvehicles       INT           NULL,
    monthlyprice      DECIMAL(10,2) NULL,
    trialdays         INT           NOT NULL DEFAULT 0,
    features          LONGTEXT      NULL CHECK (features IS NULL OR JSON_VALID(features)),
    active            TINYINT(1)    NOT NULL DEFAULT 1,
    sortorder         INT           NOT NULL DEFAULT 0,
    stripeproductid   VARCHAR(64)   NULL,
    stripepriceid     VARCHAR(64)   NULL,
    stripepriceamount DECIMAL(10,2) NULL,
    added             DATETIME      NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated           DATETIME      NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_plans_code (code),
    CONSTRAINT ck_plans_range CHECK (minvehicles >= 1 AND (maxvehicles IS NULL OR maxvehicles >= minvehicles)),
    CONSTRAINT ck_plans_price CHECK (monthlyprice IS NULL OR monthlyprice >= 0),
    CONSTRAINT ck_plans_trial CHECK (trialdays >= 0 AND trialdays <= 90)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS subscriptions (
    recordid             VARCHAR(36)   NOT NULL,
    accountid            VARCHAR(36)   NOT NULL,
    planid               VARCHAR(36)   NOT NULL,
    status               VARCHAR(12)   NOT NULL,     -- trialing | active | past_due | canceled | incomplete
    fleetsize            INT           NOT NULL,
    monthlyprice         DECIMAL(10,2) NOT NULL,
    stripesubscriptionid VARCHAR(64)   NULL,
    trialend             DATETIME      NULL,
    currentperiodend     DATETIME      NULL,
    startedon            DATETIME      NOT NULL DEFAULT UTC_TIMESTAMP(),
    canceledon           DATETIME      NULL,
    added                DATETIME      NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated              DATETIME      NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_subscriptions_stripe (stripesubscriptionid),
    KEY ix_subscriptions_account (accountid, startedon),
    CONSTRAINT fk_subscriptions_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_subscriptions_plan FOREIGN KEY (planid) REFERENCES plans (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The application's choice, before the subscription exists.
ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS fleetsize INT         NULL AFTER signupsource,
    ADD COLUMN IF NOT EXISTS planid    VARCHAR(36) NULL AFTER fleetsize;

-- Example tiers - PLACEHOLDER PRICES (roughly $15-30 per vehicle per month at the top of each
-- range). Set real prices in the admin portal before taking signups.
INSERT IGNORE INTO plans (recordid, code, name, description, minvehicles, maxvehicles, monthlyprice, trialdays, features, sortorder) VALUES
  ('b1a7c0de-0001-4a00-9000-000000000001', 'STARTER',    'Starter',    'For small operators getting audit-ready', 1, 5, 99.00, 14,
   '["Up to 5 vehicles", "Unlimited drivers and trips", "Exposure dashboard and pre-billing scrub", "Audit packets"]', 1),
  ('b1a7c0de-0001-4a00-9000-000000000002', 'GROWTH',     'Growth',     'For growing fleets with multiple brokers', 6, 15, 249.00, 14,
   '["6-15 vehicles", "Everything in Starter", "Multi-broker rule sets", "Priority support"]', 2),
  ('b1a7c0de-0001-4a00-9000-000000000003', 'FLEET',      'Fleet',      'For established fleets', 16, 35, 499.00, 14,
   '["16-35 vehicles", "Everything in Growth", "Onboarding assistance"]', 3),
  ('b1a7c0de-0001-4a00-9000-000000000004', 'PRO',        'Pro',        'For large regional operators', 36, 50, 799.00, 14,
   '["36-50 vehicles", "Everything in Fleet", "Dedicated success manager"]', 4),
  ('b1a7c0de-0001-4a00-9000-000000000005', 'ENTERPRISE', 'Enterprise', 'For fleets over 50 vehicles - priced to your operation', 51, NULL, NULL, 0,
   '["51+ vehicles", "Custom pricing and terms", "API and dispatch integrations"]', 5);
