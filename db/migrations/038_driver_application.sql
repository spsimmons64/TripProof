-- ################################################################################################
-- # 038 - the online driver application, and signatures.
-- #
-- # A driver applies at /account/<number>/apply without a login. They are identified by date of
-- # birth and Social Security number: the SSN is never stored in the clear - `ssnhash` is an HMAC
-- # under the PHI key, enough to recognise a returning applicant within one account and nothing
-- # else. The number itself lives in the phi table like every other identifier.
-- #
-- # drivers.status    application  a form in progress or submitted, not yet a working driver
-- #                   pending      submitted and under review by the account
-- #                   active       cleared to drive
-- #                   inactive     no longer driving
-- #
-- # signatures        one per signer: the driver, a user of the account, or a third party. The
-- #                   driver and the account user prove who they are with date of birth + SSN; the
-- #                   signature is adopted once, then reused to sign every document.
-- # documentsignatures  each signing event: which signature, which document, the SHA-256 of the
-- #                   exact text signed, and when, by whom and from where.
-- ################################################################################################
ALTER TABLE drivers
    ADD COLUMN IF NOT EXISTS status  VARCHAR(12) NOT NULL DEFAULT 'active' AFTER lastname,
    ADD COLUMN IF NOT EXISTS ssnhash CHAR(64)    NULL AFTER dob;

ALTER TABLE drivers
    ADD CONSTRAINT IF NOT EXISTS ck_drivers_status
        CHECK (status IN ('application', 'pending', 'active', 'inactive'));

CREATE INDEX IF NOT EXISTS ix_drivers_ssnhash ON drivers (accountid, ssnhash);

CREATE TABLE IF NOT EXISTS driverapplications (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    driverid     VARCHAR(36)  NOT NULL,
    status       VARCHAR(12)  NOT NULL DEFAULT 'started',   -- started | submitted | approved | rejected
    step         INT          NOT NULL DEFAULT 1,           -- furthest step reached
    data         LONGTEXT     NULL CHECK (data IS NULL OR JSON_VALID(data)),
    startedon    DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated      DATETIME     NULL,
    submittedon  DATETIME     NULL,
    reviewedby   VARCHAR(36)  NULL,
    reviewedon   DATETIME     NULL,
    ip           VARCHAR(45)  NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_driverapplications_driver (driverid),
    KEY ix_driverapplications_account (accountid, status),
    CONSTRAINT fk_driverapplications_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_driverapplications_driver FOREIGN KEY (driverid) REFERENCES drivers (recordid),
    CONSTRAINT ck_driverapplications_status CHECK (status IN ('started', 'submitted', 'approved', 'rejected'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS signatures (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    signertype   VARCHAR(12)  NOT NULL,                     -- driver | user | thirdparty
    signerid     VARCHAR(36)  NULL,                         -- driverid or userid; null for a third party
    signername   VARCHAR(128) NOT NULL,                     -- the name of record
    typedname    VARCHAR(128) NOT NULL,                     -- what they typed as their signature
    fontkey      VARCHAR(24)  NOT NULL DEFAULT 'signature', -- which signature face it is drawn in
    email        VARCHAR(255) NULL,                         -- third parties are reached by email
    role         VARCHAR(64)  NULL,                         -- third party's relationship (examiner, employer…)
    verifiedby   VARCHAR(12)  NOT NULL,                     -- dob_ssn | login | link
    createdon    DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    ip           VARCHAR(45)  NULL,
    useragent    VARCHAR(255) NULL,
    revokedon    DATETIME     NULL,
    PRIMARY KEY (recordid),
    KEY ix_signatures_signer (accountid, signertype, signerid),
    CONSTRAINT fk_signatures_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT ck_signatures_type CHECK (signertype IN ('driver', 'user', 'thirdparty')),
    CONSTRAINT ck_signatures_verified CHECK (verifiedby IN ('dob_ssn', 'login', 'link'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS documentsignatures (
    recordid       VARCHAR(36)  NOT NULL,
    accountid      VARCHAR(36)  NOT NULL,
    signatureid    VARCHAR(36)  NOT NULL,
    doctype        VARCHAR(32)  NOT NULL,                   -- I9 | W4 | FCRA_AUTH | DRUG_POLICY | …
    ownertype      VARCHAR(8)   NOT NULL DEFAULT 'driver',
    ownerid        VARCHAR(36)  NOT NULL,
    contentsha256  CHAR(64)     NOT NULL,                   -- the exact text that was signed
    contentversion VARCHAR(16)  NULL,
    signedon       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    ip             VARCHAR(45)  NULL,
    useragent      VARCHAR(255) NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_documentsignatures_once (ownertype, ownerid, doctype, signatureid),
    KEY ix_documentsignatures_owner (accountid, ownertype, ownerid),
    CONSTRAINT fk_documentsignatures_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_documentsignatures_signature FOREIGN KEY (signatureid) REFERENCES signatures (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- A driver's SSN is PHI-grade personal data and goes in the same encrypted table as trip details,
-- so the owner types have to admit it.
ALTER TABLE phi DROP CONSTRAINT IF EXISTS ck_phi_owner;
ALTER TABLE phi ADD CONSTRAINT IF NOT EXISTS ck_phi_owner
    CHECK (ownertype IN ('trip', 'leg', 'batch', 'driver'));
