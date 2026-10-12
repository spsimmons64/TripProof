-- ################################################################################################
-- # 050 - each account's own driver qualification list.
-- #
-- # compliancedocs is the catalog: what the law and the programmes ask of a driver, with the
-- # citation behind each one. It is ours, and it changes as rules change. What a given company
-- # asks of its own drivers is not ours - it is theirs, and it must not move under them because we
-- # edited a shared table.
-- #
-- # So an account gets its own copy at creation, and the driver review screen reads this table.
-- #
-- #   obligation  required     must be on file before this company hires anyone
-- #               conditional  required once its condition holds (a commercial driver, say)
-- #               recommended  wanted, but nobody is stopped for it
-- #               off          this company does not ask for it
-- #
-- # An account may raise an item, lower a recommended one, or switch a recommended one off. It may
-- # not switch off something the law requires: `catalog` remembers where a row came from, and the
-- # API refuses to weaken a row the catalog calls required or conditional. An account may also add
-- # its own items, which have no catalog row behind them (catalog = 0).
-- ################################################################################################
CREATE TABLE IF NOT EXISTS accountqualifications (
    recordid    VARCHAR(36)  NOT NULL,
    accountid   VARCHAR(36)  NOT NULL,
    code        VARCHAR(48)  NOT NULL,
    catalog     TINYINT(1)   NOT NULL DEFAULT 1,   -- 0 = the account's own item
    name        VARCHAR(160) NULL,                 -- set only for the account's own items
    obligation  VARCHAR(12)  NOT NULL,
    requiredfor VARCHAR(8)   NOT NULL DEFAULT 'both',
    note        VARCHAR(512) NULL,                 -- what this company means by it
    sortorder   INT          NOT NULL DEFAULT 0,
    added       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated     DATETIME     NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_accountqual_code (accountid, code),
    CONSTRAINT fk_accountqual_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT ck_accountqual_obligation CHECK (obligation IN ('required', 'conditional', 'recommended', 'off')),
    CONSTRAINT ck_accountqual_requiredfor CHECK (requiredfor IN ('both', 'cdl', 'noncdl', 'none'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Every account that already exists starts from the catalog as it stands today.
INSERT IGNORE INTO accountqualifications (recordid, accountid, code, catalog, obligation, requiredfor, sortorder)
SELECT UUID(), a.recordid, c.code, 1, c.obligation, c.requiredfor, c.sortorder
FROM accounts a
CROSS JOIN compliancedocs c
WHERE a.deleted IS NULL AND a.platform = 0 AND c.active = 1 AND c.subject = 'driver';
