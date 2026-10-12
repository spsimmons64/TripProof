-- ################################################################################################
-- # 006 - customer profile and password invitations.
-- #
-- # Every customer gets an account number from a sequence (100001, 100002, ...), assigned on
-- # creation and never reused or edited. The admin contact is not copied onto the account: it IS the
-- # customer's primary login (primaryuserid), so its name and email live on that user.
-- #
-- # Passwords are no longer handed out. A new user, or anyone an admin resets, gets an emailed
-- # single-use link. Only the SHA-256 of the link's token is stored; a link expires, is spent on use,
-- # and issuing a new one retires any older unused ones for that user.
-- ################################################################################################
CREATE SEQUENCE IF NOT EXISTS accountnumbers START WITH 100001 INCREMENT BY 1 NOCACHE;

ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS accountnumber INT          NULL AFTER recordid,
    ADD COLUMN IF NOT EXISTS address1      VARCHAR(128) NULL AFTER name,
    ADD COLUMN IF NOT EXISTS address2      VARCHAR(128) NULL AFTER address1,
    ADD COLUMN IF NOT EXISTS city          VARCHAR(64)  NULL AFTER address2,
    ADD COLUMN IF NOT EXISTS zip           VARCHAR(10)  NULL AFTER state,
    ADD COLUMN IF NOT EXISTS phone         VARCHAR(20)  NULL AFTER zip,
    ADD COLUMN IF NOT EXISTS fax           VARCHAR(20)  NULL AFTER phone,
    ADD COLUMN IF NOT EXISTS ein           VARCHAR(10)  NULL AFTER fax,
    ADD COLUMN IF NOT EXISTS primaryuserid VARCHAR(36)  NULL AFTER medicaidid;

ALTER TABLE accounts ADD UNIQUE KEY IF NOT EXISTS ux_accounts_accountnumber (accountnumber);

-- Existing customers get numbers in the order they joined; their earliest owner becomes the admin.
UPDATE accounts SET accountnumber = NEXT VALUE FOR accountnumbers
WHERE accountnumber IS NULL AND platform = 0
ORDER BY added, recordid;

UPDATE accounts a SET primaryuserid = (
    SELECT u.recordid FROM users u
    WHERE u.accountid = a.recordid AND u.role = 'owner' AND u.deleted IS NULL
    ORDER BY u.added, u.recordid LIMIT 1)
WHERE a.primaryuserid IS NULL AND a.platform = 0;

CREATE TABLE IF NOT EXISTS passwordtokens (
    recordid   VARCHAR(36)  NOT NULL,
    userid     VARCHAR(36)  NOT NULL,
    tokenhash  CHAR(64)     NOT NULL,
    purpose    VARCHAR(8)   NOT NULL,            -- invite | reset
    expires    DATETIME     NOT NULL,
    usedon     DATETIME     NULL,
    createdby  VARCHAR(36)  NULL,
    added      DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_passwordtokens_hash (tokenhash),
    KEY ix_passwordtokens_user (userid),
    CONSTRAINT fk_passwordtokens_user FOREIGN KEY (userid) REFERENCES users (recordid),
    CONSTRAINT ck_passwordtokens_purpose CHECK (purpose IN ('invite','reset'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
