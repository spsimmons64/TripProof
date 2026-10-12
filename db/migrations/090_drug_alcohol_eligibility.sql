-- ################################################################################################
-- # 090 - qualified is not the same as eligible.
-- #
-- # A driver's file can be complete - licence, medical card, driving record, annual review - while
-- # the driver is forbidden to touch a commercial vehicle. 49 CFR 382.501 prohibits an employer
-- # from letting a driver perform any safety-sensitive function after a positive test or a refusal,
-- # until the return-to-duty process of 382.503 and Part 40 subpart O has been completed. A
-- # Clearinghouse query returning "prohibited" says the same thing (382.701), and actual knowledge
-- # of a violation (382.107) says it with no test at all.
-- #
-- # So eligibility is kept apart from qualification, because it fails on its own terms and it
-- # overrides: whatever else is in order, a prohibited driver may not drive a covered vehicle.
-- #
-- # Two records:
-- #   drugtests           each test taken, why it was taken, and what came back
-- #   driverprohibitions  a bar on safety-sensitive work, where it came from, and what lifted it
-- #
-- # A cancelled test is not a test (40.23(f)): it neither satisfies the pre-employment requirement
-- # nor prohibits anybody, and a new collection is owed. That is why the result is recorded as what
-- # it was rather than as passed or failed.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS drugtests (
    recordid    VARCHAR(36)  NOT NULL,
    accountid   VARCHAR(36)  NOT NULL,
    driverid    VARCHAR(36)  NOT NULL,
    reason      VARCHAR(24)  NOT NULL,      -- why it was taken: preemployment, random, ...
    collectedon DATE         NOT NULL,
    result      VARCHAR(24)  NOT NULL,      -- negative | negativedilute | positive | refusal | ...
    dot         TINYINT(1)   NOT NULL DEFAULT 1,   -- a DOT test, or the company's own
    documentid  VARCHAR(36)  NULL,
    note        VARCHAR(512) NULL,
    enteredby   VARCHAR(36)  NULL,
    createdon   DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (recordid),
    KEY ix_drugtests_driver (accountid, driverid, collectedon),
    CONSTRAINT fk_drugtests_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_drugtests_driver FOREIGN KEY (driverid) REFERENCES drivers (recordid),
    CONSTRAINT ck_drugtests_reason CHECK (reason IN ('preemployment', 'random', 'postaccident',
        'reasonablesuspicion', 'returntoduty', 'followup')),
    CONSTRAINT ck_drugtests_result CHECK (result IN ('negative', 'negativedilute', 'positive',
        'refusal', 'adulterated', 'substituted', 'cancelled', 'pending'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS driverprohibitions (
    recordid      VARCHAR(36)  NOT NULL,
    accountid     VARCHAR(36)  NOT NULL,
    driverid      VARCHAR(36)  NOT NULL,
    source        VARCHAR(24)  NOT NULL,    -- test | clearinghouse | actualknowledge
    reason        VARCHAR(255) NOT NULL,    -- said plainly, as the file should read
    testid        VARCHAR(36)  NULL,        -- the test that caused it, where one did
    startedon     DATE         NOT NULL,
    -- The return-to-duty process, step by step. A prohibition lifts on the last of them, never
    -- before: SAP evaluation, the education or treatment the SAP prescribed, the SAP's follow-up
    -- determination, and a negative return-to-duty test (40.305).
    sapname       VARCHAR(128) NULL,
    sapevaluatedon DATE        NULL,
    sapcompliedon DATE         NULL,
    rtdtestid     VARCHAR(36)  NULL,
    clearedon     DATE         NULL,
    clearedby     VARCHAR(36)  NULL,
    -- What survives the prohibition: the SAP's follow-up testing plan runs on afterwards
    -- (40.307, 382.311), at least six tests in the first twelve months.
    followuptests INT          NULL,
    followupuntil DATE         NULL,
    note          VARCHAR(512) NULL,
    enteredby     VARCHAR(36)  NULL,
    createdon     DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (recordid),
    KEY ix_driverprohibitions_driver (accountid, driverid, clearedon),
    CONSTRAINT fk_driverprohibitions_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_driverprohibitions_driver FOREIGN KEY (driverid) REFERENCES drivers (recordid),
    CONSTRAINT ck_driverprohibitions_source CHECK (source IN ('test', 'clearinghouse', 'actualknowledge'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- A check of its own: not a document that expires, but a person who may not drive today.
ALTER TABLE requirements DROP CONSTRAINT IF EXISTS ck_requirements_kind;
ALTER TABLE requirements
    ADD CONSTRAINT ck_requirements_kind CHECK (kind IN ('credential', 'vehiclemileage', 'vehicleage',
        'driverage', 'licenseyears', 'tripevidence', 'obligation', 'licenceclass', 'annualreview',
        'eligibility'));
