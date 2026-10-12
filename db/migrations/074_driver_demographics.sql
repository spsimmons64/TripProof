-- ################################################################################################
-- # 074 - the driver's own record: where they live, and every licence they hold.
-- #
-- # Both were trapped inside the application's JSON, which is a record of what was said at the time
-- # rather than a record of the person. An office that corrects an address, or files a renewed
-- # licence, is not editing what the applicant swore to - it is keeping the driver's file current.
-- #
-- # A driver holds licences over time, and exactly one of them is the one they drive on. That one is
-- # copied onto the driver row as well, because every trip check reads it there.
-- ################################################################################################
ALTER TABLE drivers
    ADD COLUMN address1 VARCHAR(128) NULL AFTER lastname,
    ADD COLUMN address2 VARCHAR(128) NULL AFTER address1,
    ADD COLUMN city     VARCHAR(64)  NULL AFTER address2,
    ADD COLUMN state    CHAR(2)      NULL AFTER city,
    ADD COLUMN zip      VARCHAR(10)  NULL AFTER state;

CREATE TABLE IF NOT EXISTS driverlicenses (
    recordid       VARCHAR(36) NOT NULL,
    accountid      VARCHAR(36) NOT NULL,
    driverid       VARCHAR(36) NOT NULL,
    number         VARCHAR(32) NOT NULL,
    state          CHAR(2)     NOT NULL,
    classification VARCHAR(2)  NULL,
    endorsements   VARCHAR(16) NULL,
    issued         DATE        NULL,
    expires        DATE        NULL,
    active         TINYINT(1)  NOT NULL DEFAULT 0,   -- the one they drive on
    note           VARCHAR(255) NULL,
    added          DATETIME    NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated        DATETIME    NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_driverlicenses (accountid, driverid, state, number),
    KEY ix_driverlicenses_driver (driverid, active),
    CONSTRAINT fk_driverlicenses_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_driverlicenses_driver FOREIGN KEY (driverid) REFERENCES drivers (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- What the applications already on file said about where each driver lives.
UPDATE drivers d
  JOIN driverapplications a ON a.driverid = d.recordid
   SET d.address1 = COALESCE(d.address1, JSON_UNQUOTE(JSON_EXTRACT(a.data, '$.steps."1".address1'))),
       d.address2 = COALESCE(d.address2, JSON_UNQUOTE(JSON_EXTRACT(a.data, '$.steps."1".address2'))),
       d.city     = COALESCE(d.city,     JSON_UNQUOTE(JSON_EXTRACT(a.data, '$.steps."1".city'))),
       d.state    = COALESCE(d.state,    JSON_UNQUOTE(JSON_EXTRACT(a.data, '$.steps."1".state'))),
       d.zip      = COALESCE(d.zip,      JSON_UNQUOTE(JSON_EXTRACT(a.data, '$.steps."1".zip')))
 WHERE JSON_EXTRACT(a.data, '$.steps."1".address1') IS NOT NULL;
