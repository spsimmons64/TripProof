-- ################################################################################################
-- # 003 - platform administration, the regulations library, draft rule sets, and the requirement
-- # kinds the regulatory catalog needs (minimum coverage amounts, driver age, years licensed,
-- # vehicle mileage, per-trip evidence).
-- ################################################################################################

-- ------------------------------------------------------------------------------------------------
-- Platform administration. TripProof staff are users of a flagged internal account; platformrole
-- opens the admin portal. Customer accounts can be suspended, which signs every user out.
-- ------------------------------------------------------------------------------------------------
ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS platform TINYINT(1)  NOT NULL DEFAULT 0 AFTER medicaidid,
    ADD COLUMN IF NOT EXISTS status   VARCHAR(12) NOT NULL DEFAULT 'active' AFTER platform;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS platformrole VARCHAR(12) NULL AFTER role;     -- superadmin | support

-- ------------------------------------------------------------------------------------------------
-- Sources - where a rule was read from. A statute, a handbook, a broker contract, or a secondary
-- guide. reliability says how far it can be trusted on its own: a rule set built only on secondary
-- sources stays a draft until someone confirms it against a primary one.
-- ------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sources (
    recordid     VARCHAR(36)  NOT NULL,
    title        VARCHAR(255) NOT NULL,
    publisher    VARCHAR(128) NULL,
    author       VARCHAR(128) NULL,
    url          VARCHAR(512) NULL,
    kind         VARCHAR(12)  NOT NULL,            -- statute | regulation | handbook | contract | guide | other
    reliability  VARCHAR(10)  NOT NULL,            -- primary | secondary
    publishedon  DATE         NULL,
    accessedon   DATE         NULL,
    snapshot     VARCHAR(255) NULL,                -- repo path of the saved extraction, e.g. db/sources/...
    notes        TEXT         NULL,
    added        DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated      DATETIME     NULL,
    PRIMARY KEY (recordid),
    CONSTRAINT ck_sources_kind CHECK (kind IN ('statute','regulation','handbook','contract','guide','other')),
    CONSTRAINT ck_sources_reliability CHECK (reliability IN ('primary','secondary'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Regulations - the library of legal authorities requirements cite (42 CFR 455.450, 49 CFR 382,
-- Fla. Stat. 435.04 ...). jurisdiction is 'US' for federal or a state code.
CREATE TABLE IF NOT EXISTS regulations (
    recordid     VARCHAR(36)  NOT NULL,
    citation     VARCHAR(96)  NOT NULL,
    title        VARCHAR(255) NOT NULL,
    jurisdiction VARCHAR(4)   NOT NULL DEFAULT 'US',
    agency       VARCHAR(64)  NULL,
    category     VARCHAR(16)  NOT NULL,            -- enrollment | driver | vehicle | insurance | privacy | billing | audit | accessibility | testing | safety
    summary      TEXT         NULL,
    url          VARCHAR(512) NULL,
    sourceid     VARCHAR(36)  NULL,
    verified     TINYINT(1)   NOT NULL DEFAULT 0,  -- 1 = read against the primary text
    added        DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated      DATETIME     NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_regulations_citation (citation),
    CONSTRAINT fk_regulations_source FOREIGN KEY (sourceid) REFERENCES sources (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------------------------
-- Rule sets gain a lifecycle. Only published versions are evaluated. Drafts can be edited freely
-- and may overlap anything; publishing checks the dates against the other published versions of
-- the family. Retired versions stay for the record (old runs reference their requirements).
-- ------------------------------------------------------------------------------------------------
ALTER TABLE rulesets
    ADD COLUMN IF NOT EXISTS status      VARCHAR(10) NOT NULL DEFAULT 'published' AFTER verified,
    ADD COLUMN IF NOT EXISTS sourceid    VARCHAR(36) NULL AFTER source,
    ADD COLUMN IF NOT EXISTS publishedby VARCHAR(36) NULL,
    ADD COLUMN IF NOT EXISTS publishedon DATETIME    NULL,
    ADD COLUMN IF NOT EXISTS updated     DATETIME    NULL;

ALTER TABLE rulesets
    ADD CONSTRAINT IF NOT EXISTS ck_rulesets_status CHECK (status IN ('draft','published','retired')),
    ADD FOREIGN KEY IF NOT EXISTS fk_rulesets_source (sourceid) REFERENCES sources (recordid);

-- ------------------------------------------------------------------------------------------------
-- Requirements: more kinds, a 'trip' subject, and links to the regulation and source behind them.
--   credential      (existing) + params {"minamount": 1000000} for coverage limits on a COI
--   vehicleage      (existing) params {"maxyears": 10}
--   vehiclemileage  params {"maxmiles": 300000}        - vehicles.odometer
--   driverage       params {"minyears": 21}            - drivers.dob
--   licenseyears    params {"minyears": 3}             - drivers.licensesince
--   tripevidence    params {"field": "signature"|"gps"} - subject 'trip'; the leg's own evidence
-- ------------------------------------------------------------------------------------------------
ALTER TABLE requirements
    DROP CONSTRAINT IF EXISTS ck_requirements_kind,
    DROP CONSTRAINT IF EXISTS ck_requirements_subject;
ALTER TABLE requirements
    ADD CONSTRAINT IF NOT EXISTS ck_requirements_kind CHECK (kind IN ('credential','vehicleage','vehiclemileage','driverage','licenseyears','tripevidence')),
    ADD CONSTRAINT IF NOT EXISTS ck_requirements_subject CHECK (subject IN ('driver','vehicle','company','trip')),
    ADD COLUMN IF NOT EXISTS regulationid VARCHAR(36) NULL AFTER citation,
    ADD COLUMN IF NOT EXISTS sourceid     VARCHAR(36) NULL AFTER regulationid,
    ADD COLUMN IF NOT EXISTS updated      DATETIME    NULL;
ALTER TABLE requirements
    ADD FOREIGN KEY IF NOT EXISTS fk_requirements_regulation (regulationid) REFERENCES regulations (recordid),
    ADD FOREIGN KEY IF NOT EXISTS fk_requirements_source (sourceid) REFERENCES sources (recordid);

-- ------------------------------------------------------------------------------------------------
-- Credential types. maxagedays stays a hard freshness limit (a check older than N days no longer
-- counts, whatever is printed). defaultvaliddays is new: how long a certificate is good for when no
-- expiry is printed on it (CPR every 2 years). hasamount marks types that carry a dollar limit.
-- ------------------------------------------------------------------------------------------------
ALTER TABLE credentialtypes
    ADD COLUMN IF NOT EXISTS defaultvaliddays INT         NULL AFTER maxagedays,
    ADD COLUMN IF NOT EXISTS hasamount        TINYINT(1)  NOT NULL DEFAULT 0 AFTER defaultvaliddays,
    ADD COLUMN IF NOT EXISTS category         VARCHAR(16) NULL AFTER hasamount,
    ADD COLUMN IF NOT EXISTS regulationid     VARCHAR(36) NULL,
    ADD COLUMN IF NOT EXISTS active           TINYINT(1)  NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS updated          DATETIME    NULL;

ALTER TABLE credentials
    ADD COLUMN IF NOT EXISTS amount DECIMAL(14,2) NULL AFTER issuer;      -- coverage limit on a COI

ALTER TABLE drivers
    ADD COLUMN IF NOT EXISTS dob          DATE NULL AFTER lastname,
    ADD COLUMN IF NOT EXISTS licensesince DATE NULL AFTER licensestate;    -- first licensed, for the held-3-years rule

ALTER TABLE vehicles
    ADD COLUMN IF NOT EXISTS odometer     INT  NULL AFTER modelyear,
    ADD COLUMN IF NOT EXISTS odometerasof DATE NULL AFTER odometer,
    ADD COLUMN IF NOT EXISTS gvwr         INT  NULL AFTER odometerasof;

ALTER TABLE brokers
    ADD COLUMN IF NOT EXISTS website VARCHAR(255) NULL,
    ADD COLUMN IF NOT EXISTS notes   TEXT NULL,
    ADD COLUMN IF NOT EXISTS active  TINYINT(1) NOT NULL DEFAULT 1;

-- ------------------------------------------------------------------------------------------------
-- The overlap rule now applies to published versions only.
-- ------------------------------------------------------------------------------------------------
DELIMITER $$

CREATE OR REPLACE TRIGGER tr_rulesets_nooverlap_ins BEFORE INSERT ON rulesets FOR EACH ROW
BEGIN
    IF NEW.status = 'published' AND EXISTS (
            SELECT 1 FROM rulesets r
            WHERE r.family = NEW.family AND r.status = 'published'
              AND r.effectivefrom <= COALESCE(NEW.effectiveto, '9999-12-31')
              AND COALESCE(r.effectiveto, '9999-12-31') >= NEW.effectivefrom) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'rulesets: overlapping published versions in one family';
    END IF;
END$$

CREATE OR REPLACE TRIGGER tr_rulesets_nooverlap_upd BEFORE UPDATE ON rulesets FOR EACH ROW
BEGIN
    IF NEW.status = 'published' AND EXISTS (
            SELECT 1 FROM rulesets r
            WHERE r.family = NEW.family AND r.status = 'published' AND r.recordid <> NEW.recordid
              AND r.effectivefrom <= COALESCE(NEW.effectiveto, '9999-12-31')
              AND COALESCE(r.effectiveto, '9999-12-31') >= NEW.effectivefrom) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'rulesets: overlapping published versions in one family';
    END IF;
END$$

DELIMITER ;
