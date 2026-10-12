-- How a company takes a card.
--
-- NOT TripProof's own Stripe account. That one is in the environment and charges customers
-- their subscription. This is the OTHER direction entirely: a transport company charging a
-- passenger for a private-pay trip, through whichever processor that company already banks
-- with. Two things called "the payment gateway" in one system is how somebody ends up
-- refunding a passenger out of TripProof's merchant account, so this one is named for whose
-- money moves through it.
--
-- Two tables because there are two decisions, made by different people:
--   paymentgateways  - which adapters TripProof offers at all. A platform decision.
--   accountgateways  - which one a company uses, and its keys. The company's decision, and
--                      its secret.
--
-- The adapters themselves - what each one is called, which fields it needs, which of those
-- are secret - live in code (app/gateways.py), not here. A field list is a property of the
-- processor's API, and a row in a table that has to be migrated every time a processor adds
-- a field is a row that will be wrong.

CREATE TABLE IF NOT EXISTS paymentgateways (
  code       VARCHAR(32)  NOT NULL,
  -- Offered to companies at all. Off is how an adapter is withdrawn without deleting the
  -- configuration of everybody already using it.
  active     TINYINT(1)   NOT NULL DEFAULT 1,
  sortorder  INT          NOT NULL DEFAULT 0,
  note       VARCHAR(255)     NULL,
  updated    DATETIME         NULL,
  PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS accountgateways (
  recordid     VARCHAR(36) NOT NULL,
  accountid    VARCHAR(36) NOT NULL,
  gatewaycode  VARCHAR(32) NOT NULL,
  -- test | live. On its own row rather than inside the sealed blob, because "is this company
  -- pointed at a sandbox" is a question support has to be able to answer without holding the
  -- key to read the answer.
  mode         VARCHAR(8)  NOT NULL DEFAULT 'test',
  -- Sealed with the same AES-256-GCM keys as PHI (app/crypto.py), bound to the account and
  -- the adapter so a blob lifted from one row cannot be opened in another. NOT in the `phi`
  -- table: a merchant key is not patient data, and the PHI vault's access logging says
  -- something about who read a passenger's details that is not true of a config read.
  keyversion   INT             NULL,
  credentials  TEXT            NULL,
  -- Which one is in use. At most one per account, enforced in app/gateways.py.
  active       TINYINT(1)  NOT NULL DEFAULT 0,
  addedby      VARCHAR(36)     NULL,
  added        DATETIME    NOT NULL DEFAULT UTC_TIMESTAMP(),
  updated      DATETIME        NULL,
  PRIMARY KEY (recordid),
  UNIQUE KEY ux_accountgateways (accountid, gatewaycode),
  CONSTRAINT fk_accountgateways_account
    FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
