-- ################################################################################################
-- # 049 - the hiring file: what has been ordered, what has come back, what is still outstanding.
-- #
-- # The catalog already says what a driver needs (compliancedocs, subject 'driver', requiredfor
-- # 'both' | 'cdl' | 'noncdl' | 'none'). This is the other half: one row per driver per catalog
-- # item, recording where that item stands while the office works the application through.
-- #
-- #   todo      nothing yet
-- #   ordered   asked for and waiting - an MVR, a PSP report, a Clearinghouse query
-- #   received  it is in, and `documentid` is the copy on file
-- #   waived    deliberately not required for this driver; `note` says why
-- #
-- # A screening result that also belongs in the credential record (an MVR, a medical card) is
-- # written to `credentials` as well, so the trip rules see it; this table is the hiring story.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS driverqualifications (
    recordid    VARCHAR(36)  NOT NULL,
    accountid   VARCHAR(36)  NOT NULL,
    driverid    VARCHAR(36)  NOT NULL,
    code        VARCHAR(48)  NOT NULL,          -- compliancedocs.code
    state       VARCHAR(10)  NOT NULL DEFAULT 'todo',
    outcome     VARCHAR(16)  NULL,              -- clear | review | flagged
    orderedon   DATETIME     NULL,
    orderedby   VARCHAR(36)  NULL,
    completedon DATETIME     NULL,
    completedby VARCHAR(36)  NULL,
    documentid  VARCHAR(36)  NULL,
    note        VARCHAR(512) NULL,
    added       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated     DATETIME     NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_driverqual_item (accountid, driverid, code),
    KEY ix_driverqual_driver (driverid, state),
    CONSTRAINT fk_driverqual_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_driverqual_driver FOREIGN KEY (driverid) REFERENCES drivers (recordid),
    CONSTRAINT fk_driverqual_document FOREIGN KEY (documentid) REFERENCES documents (recordid),
    CONSTRAINT ck_driverqual_state CHECK (state IN ('todo', 'ordered', 'received', 'waived')),
    CONSTRAINT ck_driverqual_outcome CHECK (outcome IS NULL OR outcome IN ('clear', 'review', 'flagged'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
