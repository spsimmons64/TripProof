-- What a trip is worth.
--
-- NOT `feeschedule`. That table already exists and is the other side of the business: what
-- TripProof charges ITS customers for pass-through services - an MVR, a CDLIS check, a
-- Clearinghouse query. Platform-wide, five rows, nothing to do with a transport company
-- pricing a journey. Two things called a fee schedule in one schema is how somebody ends up
-- billing a passenger $25 for a motor vehicle record, so this one is named for whose money
-- it is.
--
-- A schedule belongs to an account and to a payer: the company's own private pay prices, or
-- the rates a particular broker contracts to pay. Both are needed and they are not the same
-- number - what you charge and what you are paid are different facts, and a product that
-- conflates them cannot tell you where the shortfall is.
--
-- Effective dated, and superseded rather than edited. A contract changes on a date, and a
-- trip carried last March has to be priceable at last March's rates for ever - which is why
-- the charge, when it is worked out, records WHICH rate produced it.

CREATE TABLE IF NOT EXISTS payerschedules (
  recordid     VARCHAR(36)  NOT NULL,
  accountid    VARCHAR(36)  NOT NULL,
  name         VARCHAR(120) NOT NULL,
  -- private = what this company charges a passenger directly.
  -- broker   = what a named broker contracts to pay it.
  payer        VARCHAR(16)  NOT NULL DEFAULT 'private',
  brokerid     VARCHAR(36)      NULL,
  contractref  VARCHAR(64)      NULL,
  effectivefrom DATE        NOT NULL,
  effectiveto  DATE             NULL,
  -- How the money is asked for, because it changes what else is required: a claim needs
  -- procedure codes, a broker invoice usually does not, a flat contract needs neither.
  billingmethod VARCHAR(16)     NULL,
  note         VARCHAR(512)     NULL,
  active       TINYINT(1)   NOT NULL DEFAULT 1,
  addedby      VARCHAR(36)      NULL,
  added        DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
  updated      DATETIME         NULL,
  PRIMARY KEY (recordid),
  KEY ix_payerschedules_account (accountid, payer, effectivefrom),
  CONSTRAINT fk_payerschedules_account
    FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The components. Deliberately rows rather than columns on the schedule: a base fare, a
-- mileage rate and a waiting rate are the same kind of thing with different units, and a
-- schema with `baserate` and `permile` columns cannot hold the fourth thing a contract
-- invents. Procedure code is here, on the rate, not on the service - CMS ties A0130 to
-- wheelchair van transport and S0209 to its mileage, which is two codes for one service.
CREATE TABLE IF NOT EXISTS payerrates (
  recordid     VARCHAR(36)  NOT NULL,
  accountid    VARCHAR(36)  NOT NULL,
  scheduleid   VARCHAR(36)  NOT NULL,
  -- base | mileage | waiting | flat | surcharge | noshow
  ratetype     VARCHAR(16)  NOT NULL,
  -- ambulatory | wheelchair | stretcher, or null where it applies to all of them
  servicelevel VARCHAR(16)      NULL,
  -- trip | mile | minute | block15 | hour
  unit         VARCHAR(16)  NOT NULL DEFAULT 'trip',
  amount       DECIMAL(10,2) NOT NULL,
  -- Units already covered by the base - the first N miles, the first N minutes of waiting.
  includedunits DECIMAL(10,2)   NULL,
  -- The least that is billable however short the job was.
  minimumunits DECIMAL(10,2)    NULL,
  -- whole | tenth | none
  rounding     VARCHAR(8)       NULL,
  proceduracode VARCHAR(16)     NULL,
  modifier     VARCHAR(8)       NULL,
  authrequired TINYINT(1)   NOT NULL DEFAULT 0,
  note         VARCHAR(255)     NULL,
  sortorder    INT          NOT NULL DEFAULT 0,
  added        DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
  PRIMARY KEY (recordid),
  KEY ix_payerrates_schedule (scheduleid, sortorder),
  CONSTRAINT fk_payerrates_schedule
    FOREIGN KEY (scheduleid) REFERENCES payerschedules (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
