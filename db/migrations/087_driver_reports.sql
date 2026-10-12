-- ################################################################################################
-- # 087 - the reports the office sends away for, other than driving records.
-- #
-- # A PSP report (49 U.S.C. 31150) and a CDLIS check (49 CFR 383.35, 391.23) are each one report
-- # about one driver: the FMCSA holds one crash and inspection history, and CDLIS answers one
-- # question about licences held anywhere. Neither is pulled per licence the way a state driving
-- # record is, so neither is kept that way.
-- #
-- # They move the same way a driving record does - sent for, then received with a copy and the date
-- # the report carries - so they are kept the same way, and the screening on the driver's list
-- # reads from whichever is current.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS driverreports (
    recordid   VARCHAR(36)  NOT NULL,
    accountid  VARCHAR(36)  NOT NULL,
    driverid   VARCHAR(36)  NOT NULL,
    code       VARCHAR(48)  NOT NULL,       -- the catalog item it answers: PSP_REPORT, CDLIS_CHECK
    orderedon  DATETIME     NULL,
    orderedby  VARCHAR(36)  NULL,
    issuedon   DATE         NULL,           -- the date the report itself carries
    receivedon DATETIME     NULL,
    receivedby VARCHAR(36)  NULL,
    documentid VARCHAR(36)  NULL,
    outcome    VARCHAR(16)  NULL,           -- clear | review | flagged
    note       VARCHAR(512) NULL,
    createdon  DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (recordid),
    KEY ix_driverreports_driver (accountid, driverid, code, issuedon),
    CONSTRAINT fk_driverreports_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_driverreports_driver FOREIGN KEY (driverid) REFERENCES drivers (recordid),
    CONSTRAINT ck_driverreports_outcome CHECK (outcome IS NULL OR outcome IN ('clear', 'review', 'flagged'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- What the office has already ordered or filed against these two, so nothing is asked for twice.
INSERT INTO driverreports (recordid, accountid, driverid, code, orderedon, orderedby, issuedon,
                           receivedon, receivedby, documentid, outcome, note, createdon)
SELECT UUID(), q.accountid, q.driverid, q.code, q.orderedon, q.orderedby,
       DATE(q.completedon), q.completedon, q.completedby, q.documentid, q.outcome, q.note,
       COALESCE(q.orderedon, q.completedon, q.added)
  FROM driverqualifications q
 WHERE q.code IN ('PSP_REPORT', 'CDLIS_CHECK') AND q.state IN ('ordered', 'received');
