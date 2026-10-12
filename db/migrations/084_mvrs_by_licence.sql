-- ################################################################################################
-- # 084 - driving records belong to a licence, not to a driver.
-- #
-- # A driving record is issued by the state that issued the licence, and it says nothing about what
-- # the driver did on a licence from anywhere else. A driver who has held licences in two states has
-- # two driving histories, and a carrier that pulled one of them has not seen the other - so the
-- # record is kept against the licence it was pulled on, and asking for one is asking a particular
-- # state for a particular licence.
-- #
-- # A record is ordered before it exists: the row is created when the office sends for it, and the
-- # copy and the date it carries arrive later. The credential it produces is what the rules engine
-- # reads, exactly as before, so nothing downstream has to know about any of this.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS drivermvrs (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    driverid     VARCHAR(36)  NOT NULL,
    licenseid    VARCHAR(36)  NOT NULL,       -- the licence it was pulled on
    credentialid VARCHAR(36)  NULL,           -- what the rules engine reads, once it is on file
    orderedon    DATETIME     NULL,           -- when the office sent for it
    orderedby    VARCHAR(36)  NULL,
    issuedon     DATE         NULL,           -- the date the record itself carries
    receivedon   DATETIME     NULL,           -- when it came back and was filed
    receivedby   VARCHAR(36)  NULL,
    documentid   VARCHAR(36)  NULL,
    note         VARCHAR(512) NULL,
    createdon    DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (recordid),
    KEY ix_drivermvrs_driver (accountid, driverid, issuedon),
    KEY ix_drivermvrs_licence (licenseid),
    CONSTRAINT fk_drivermvrs_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_drivermvrs_driver FOREIGN KEY (driverid) REFERENCES drivers (recordid),
    CONSTRAINT fk_drivermvrs_license FOREIGN KEY (licenseid) REFERENCES driverlicenses (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Which licence a review's record was pulled on, so a review can say whose history it read.
ALTER TABLE annualreviews ADD COLUMN mvrid VARCHAR(36) NULL AFTER credentialid;
