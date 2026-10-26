-- ################################################################################################
-- # 353 - one Social Security number, one person, across every company on TripProof.
-- #
-- # A signature is unlocked by date of birth + SSN, and until now the pair was simply taken at the
-- # first signature: any number with any birth date became somebody's identity. Each SSN is now
-- # registered once, platform-wide, with the date of birth and name it was first given. A signature
-- # is created only for a number not already registered - or for the same person, at the same
-- # company, signing both as an office user and as a driver.
-- #
-- # ssnhash is an HMAC under the PHI key with no account in it (the per-account hash on drivers
-- # and users deliberately cannot be compared across companies). keyversion says which key, so a
-- # lookup after a key rotation still finds numbers registered before it.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS signatureidentities (
    recordid     VARCHAR(36)  NOT NULL,
    ssnhash      CHAR(64)     NOT NULL,
    keyversion   INT          NOT NULL,
    dob          DATE         NOT NULL,
    fullname     VARCHAR(128) NOT NULL,
    createdon    DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_signatureidentities_ssn (ssnhash)
);

-- Who signs as that person. One row per signer; a signer belongs to one identity only.
CREATE TABLE IF NOT EXISTS signatureidentitysigners (
    identityid   VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    signertype   VARCHAR(16)  NOT NULL,
    signerid     VARCHAR(36)  NOT NULL,
    createdon    DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (accountid, signertype, signerid),
    KEY ix_signatureidentitysigners_identity (identityid)
);
