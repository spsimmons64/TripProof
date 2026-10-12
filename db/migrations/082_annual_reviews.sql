-- ################################################################################################
-- # 082 - the annual review as a signed form.
-- #
-- # 391.25(c)(2) asks the carrier to note the name of the person who performed the review, so the
-- # review is signed by them rather than merely dated by them. A review is also a yearly event: the
-- # one done this year does not replace last year's, and 391.51 keeps three years of them. So each
-- # review is its own row, with the driver and licence as they read on the day it was made - the
-- # sheet is rebuilt from that, not from what the licence says years later.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS annualreviews (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    driverid     VARCHAR(36)  NOT NULL,
    credentialid VARCHAR(36)  NULL,            -- the credential this review satisfies
    signatureid  VARCHAR(36)  NULL,            -- the reviewer's signature, as it stood that day
    reviewedon   DATE         NOT NULL,        -- the signature date on the form
    mvron        DATE         NULL,            -- the driving record that was read
    finding      VARCHAR(16)  NOT NULL,        -- qualified | notqualified
    note         VARCHAR(1000) NULL,
    reviewer     VARCHAR(128) NOT NULL,        -- who performed it, as printed under the signature
    documentid   VARCHAR(36)  NULL,            -- a copy filed instead of, or beside, the form
    filedon      DATE         NULL,            -- the date that copy carries
    snapshot     LONGTEXT     NULL,            -- driver and licence as they read at the review
    contentsha256 CHAR(64)    NULL,
    ip           VARCHAR(45)  NULL,
    useragent    VARCHAR(255) NULL,
    enteredby    VARCHAR(36)  NULL,
    createdon    DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (recordid),
    KEY ix_annualreviews_driver (accountid, driverid, reviewedon),
    CONSTRAINT fk_annualreviews_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_annualreviews_driver FOREIGN KEY (driverid) REFERENCES drivers (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
