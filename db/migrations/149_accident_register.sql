-- ################################################################################################
-- # 149 - the accident register, and the post-accident testing decision.
-- #
-- # Two regulations meet in one record and neither is served by a checkbox.
-- #
-- # 49 CFR 390.15(b) says the carrier keeps a register of accidents: when, where, how many died,
-- # how many were hurt, whether hazardous materials were released. That is a list, and it is kept
-- # whether or not anybody was tested.
-- #
-- # 49 CFR 382.303 says WHICH of those accidents require a drug and alcohol test, and the answer is
-- # not "all of them". It turns on three facts:
-- #
-- #   a human fatality                  always tested, whatever else is true
-- #   bodily injury treated away        tested ONLY if this driver was cited
-- #   disabling damage, vehicle towed   tested ONLY if this driver was cited
-- #
-- # So "was the driver cited" is not paperwork. It decides whether a test was owed, and a file that
-- # cannot answer it cannot show whether the carrier did the right thing. Each of these is stored
-- # three-valued - yes, no, or nobody has said - because "we do not know yet whether a citation was
-- # issued" is a real state in the hours after an accident and is not the same as "no".
-- #
-- # The clock matters too. An alcohol test is attempted within 8 hours and a controlled substances
-- # test within 32 (382.303(d), (e)), and where it was not done in time the carrier must keep a
-- # record saying why. That record is `nottested` - the regulation asks for the reason, so there is
-- # somewhere to write the reason.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS driveraccidents (
    recordid          VARCHAR(36)  NOT NULL PRIMARY KEY,
    accountid         VARCHAR(36)  NOT NULL,
    driverid          VARCHAR(36)  NOT NULL,

    -- The hour is part of the record, not decoration: the testing windows run from it.
    occurredon        DATETIME     NOT NULL,
    location          VARCHAR(160) NULL,

    -- 390.15(b)(1): the register's own columns.
    fatalities        INT          NULL,
    injuries          INT          NULL,
    hazmatreleased    TINYINT(1)   NULL,

    -- 382.303: what decides whether a test was owed. NULL means nobody has said yet.
    injurytreatedaway TINYINT(1)   NULL,
    towaway           TINYINT(1)   NULL,
    cited             TINYINT(1)   NULL,
    citedon           DATETIME     NULL,

    -- What was actually done about it.
    alcoholtestid     VARCHAR(36)  NULL,
    drugtestid        VARCHAR(36)  NULL,
    -- 382.303(d)(1)-(2) and (e): why a required test was not done in time. The regulation asks for
    -- the reason in writing, so the reason has a column rather than living in a general note.
    nottested         VARCHAR(512) NULL,

    note              VARCHAR(512) NULL,
    enteredby         VARCHAR(36)  NULL,
    createdon         DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),

    KEY ix_driveraccidents_driver (accountid, driverid, occurredon),
    CONSTRAINT fk_driveraccidents_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_driveraccidents_driver FOREIGN KEY (driverid) REFERENCES drivers (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
