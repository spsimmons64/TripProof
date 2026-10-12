-- ################################################################################################
-- # 099 - what came in, and whether anybody has looked at it.
-- #
-- # A document that arrives on its own - a driver signing from a link, an application submitted -
-- # is work, not news. Somebody has to read it and say they have. The event feed cannot hold that:
-- # it is pruned after a couple of days, and it deliberately carries no state, because the moment a
-- # feed holds state it becomes a second copy of the truth.
-- #
-- # So the doorbell and the inbox are two things. The event says something arrived; this row is the
-- # arrival itself, and it stays until somebody has reviewed it.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS arriveddocuments (
    recordid   VARCHAR(36)  NOT NULL,
    accountid  VARCHAR(36)  NOT NULL,
    subject    VARCHAR(24)  NOT NULL,       -- driver | vehicle | company
    subjectid  VARCHAR(36)  NULL,
    kind       VARCHAR(48)  NOT NULL,       -- signed | application-submitted | report-returned
    detail     VARCHAR(255) NULL,           -- the doctype, where there is one to open
    label      VARCHAR(160) NULL,           -- what to call it in a list
    arrivedon  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    reviewedon DATETIME     NULL,
    reviewedby VARCHAR(36)  NULL,
    PRIMARY KEY (recordid),
    KEY ix_arrived_open (accountid, reviewedon, arrivedon),
    CONSTRAINT fk_arrived_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
