-- ################################################################################################
-- # 010 - Stripe webhooks: what Stripe tells us after signup.
-- #
-- # Stripe bills subscriptions on its own (trial end, then monthly). Its webhooks keep these rows
-- # current so TripProof knows who has paid:
-- #
-- #   stripeevents   every event received, keyed by Stripe's event id. Stripe delivers at least
-- #                  once, so a repeated event is recognised here and skipped.
-- #   invoices       each Stripe invoice for a customer, as last reported (billing history).
-- #   subscriptions  + payment state: past due since when, the last payment and its failure.
-- #   accounts       + holdreason: 'billing' when the account was made inactive because the
-- #                  subscription lapsed (unpaid or canceled). Only a billing hold is lifted
-- #                  automatically when payment comes in; an account staff made inactive stays so.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS stripeevents (
    eventid       VARCHAR(64)  NOT NULL,
    type          VARCHAR(64)  NOT NULL,
    livemode      TINYINT(1)   NOT NULL DEFAULT 0,
    stripecreated DATETIME     NULL,
    accountid     VARCHAR(36)  NULL,
    outcome       VARCHAR(255) NULL,
    receivedon    DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (eventid),
    KEY ix_stripeevents_account (accountid, receivedon),
    KEY ix_stripeevents_received (receivedon)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS invoices (
    recordid        VARCHAR(36)   NOT NULL,
    accountid       VARCHAR(36)   NOT NULL,
    subscriptionid  VARCHAR(36)   NULL,
    stripeinvoiceid VARCHAR(64)   NOT NULL,
    number          VARCHAR(64)   NULL,
    status          VARCHAR(16)   NOT NULL,     -- draft | open | paid | void | uncollectible
    amountdue       DECIMAL(10,2) NOT NULL DEFAULT 0,
    amountpaid      DECIMAL(10,2) NOT NULL DEFAULT 0,
    currency        CHAR(3)       NOT NULL DEFAULT 'usd',
    periodstart     DATETIME      NULL,
    periodend       DATETIME      NULL,
    paidon          DATETIME      NULL,
    attemptcount    INT           NOT NULL DEFAULT 0,
    nextattempt     DATETIME      NULL,
    failuremessage  VARCHAR(255)  NULL,
    hostedurl       VARCHAR(1024) NULL,
    pdfurl          VARCHAR(1024) NULL,
    invoicedon      DATETIME      NULL,
    added           DATETIME      NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated         DATETIME      NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_invoices_stripe (stripeinvoiceid),
    KEY ix_invoices_account (accountid, invoicedon),
    CONSTRAINT fk_invoices_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_invoices_subscription FOREIGN KEY (subscriptionid) REFERENCES subscriptions (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE subscriptions
    ADD COLUMN IF NOT EXISTS cancelatperiodend TINYINT(1)   NOT NULL DEFAULT 0 AFTER currentperiodend,
    ADD COLUMN IF NOT EXISTS pastduesince      DATETIME     NULL AFTER cancelatperiodend,
    ADD COLUMN IF NOT EXISTS lastpaidon        DATETIME     NULL AFTER pastduesince,
    ADD COLUMN IF NOT EXISTS lastpaidamount    DECIMAL(10,2) NULL AFTER lastpaidon,
    ADD COLUMN IF NOT EXISTS lastpaymenterror  VARCHAR(255) NULL AFTER lastpaidamount,
    ADD COLUMN IF NOT EXISTS nextattempt       DATETIME     NULL AFTER lastpaymenterror,
    ADD COLUMN IF NOT EXISTS syncedon          DATETIME     NULL AFTER nextattempt;

ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS holdreason VARCHAR(12) NULL AFTER status;

ALTER TABLE accounts
    ADD CONSTRAINT IF NOT EXISTS ck_accounts_holdreason CHECK (holdreason IS NULL OR holdreason IN ('billing'));
