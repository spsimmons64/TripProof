-- ################################################################################################
-- # 387 - billing: what a driven trip is worth, how it went out, and what came back.
-- #
-- # Kept apart from the trip, so a denial or a correction never alters the evidence of what was
-- # driven. A charge line keeps the rate that produced it. A resubmission voids the old lines and
-- # writes new ones; nothing is overwritten.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS billbatches (
    recordid    VARCHAR(36)   NOT NULL,
    accountid   VARCHAR(36)   NOT NULL,
    number      INT           NOT NULL,
    payerid     VARCHAR(36)   NOT NULL,
    trips       INT           NOT NULL,
    amount      DECIMAL(12,2) NOT NULL,
    createdon   DATETIME      NOT NULL,
    createdby   VARCHAR(36)   NOT NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_billbatches_number (accountid, number)
);

CREATE TABLE IF NOT EXISTS tripcharges (
    recordid    VARCHAR(36)   NOT NULL,
    accountid   VARCHAR(36)   NOT NULL,
    tripid      VARCHAR(36)   NOT NULL,
    legid       VARCHAR(36)   NULL,
    batchid     VARCHAR(36)   NOT NULL,
    scheduleid  VARCHAR(36)   NOT NULL,
    rateid      VARCHAR(36)   NOT NULL,
    label       VARCHAR(160)  NOT NULL,
    code        VARCHAR(24)   NULL,
    units       DECIMAL(10,2) NOT NULL,
    rate        DECIMAL(10,2) NOT NULL,
    amount      DECIMAL(12,2) NOT NULL,
    voidedon    DATETIME      NULL,
    added       DATETIME      NOT NULL,
    PRIMARY KEY (recordid),
    KEY ix_tripcharges_trip (accountid, tripid),
    KEY ix_tripcharges_batch (batchid)
);

CREATE TABLE IF NOT EXISTS billpayments (
    recordid    VARCHAR(36)   NOT NULL,
    accountid   VARCHAR(36)   NOT NULL,
    tripid      VARCHAR(36)   NOT NULL,
    batchid     VARCHAR(36)   NULL,
    amount      DECIMAL(12,2) NOT NULL,
    denied      TINYINT(1)    NOT NULL DEFAULT 0,
    note        VARCHAR(600)  NULL,
    recordedon  DATETIME      NOT NULL,
    recordedby  VARCHAR(36)   NOT NULL,
    PRIMARY KEY (recordid),
    KEY ix_billpayments_trip (accountid, tripid)
);

ALTER TABLE trips ADD COLUMN IF NOT EXISTS billbatchid VARCHAR(36) NULL AFTER holdreason;
