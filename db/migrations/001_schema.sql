-- ################################################################################################
-- # TripProof schema - MariaDB 10.6+
-- #
-- # One question drives every table here: was every required credential valid at this trip leg's
-- # pickup time, under the rules of the broker that paid for it, and what is the proof?
-- #
-- # Conventions (shared with DriverFilesOnline):
-- #   recordid   VARCHAR(36) UUID primary key
-- #   added / updated / deleted   UTC DATETIMEs; `deleted` is a soft delete
-- #   accountid  on every tenant row - the API scopes every query by it
-- #
-- # Two kinds of time:
-- #   Housekeeping stamps (added, updated, started, ...) are UTC.
-- #   Business times (pickupat, issuedon, expireson, revokedon) are the operator's local wall clock,
-- #   because that is how cards are printed and how dispatch exports trips. accounts.timezone says
-- #   which zone. A card that "expires 04/02/2026" covers every pickup through 23:59:59 on 04/02.
-- #
-- # PHI (member identity, addresses, raw import rows, GPS points) lives only in `phi`, encrypted
-- # with AES-256-GCM by the API. Everything else can be reported on without touching PHI.
-- ################################################################################################

-- ================================================================================================
-- RULES - global, not tenant-scoped. Rules are data: versioned, dated, and cited.
-- ================================================================================================

CREATE TABLE IF NOT EXISTS brokers (
    recordid    VARCHAR(36)  NOT NULL,
    code        VARCHAR(32)  NOT NULL,          -- MTM, MODIVCARE, ...
    name        VARCHAR(128) NOT NULL,
    added       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated     DATETIME     NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_brokers_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- What kind of paper a credential is, and whose it is. `maxagedays` is the type's own freshness
-- limit (a background check is only good for N days no matter what is printed on it); a
-- requirement may tighten it for one broker.
CREATE TABLE IF NOT EXISTS credentialtypes (
    recordid    VARCHAR(36)  NOT NULL,
    code        VARCHAR(48)  NOT NULL,
    name        VARCHAR(128) NOT NULL,
    subject     VARCHAR(8)   NOT NULL,          -- driver | vehicle | company
    maxagedays  INT          NULL,
    description VARCHAR(512) NULL,
    added       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_credentialtypes_code (code),
    CONSTRAINT ck_credentialtypes_subject CHECK (subject IN ('driver','vehicle','company'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- A dated version of one authority's rules. brokerid NULL = the state's own baseline, which applies
-- to every trip in that state on top of the paying broker's rules. `family` groups the versions of
-- one rule set; two versions of a family may not cover the same day (enforced by trigger below).
CREATE TABLE IF NOT EXISTS rulesets (
    recordid      VARCHAR(36)  NOT NULL,
    family        VARCHAR(64)  NOT NULL,        -- e.g. FL-BASE, FL-MTM
    state         CHAR(2)      NOT NULL,
    brokerid      VARCHAR(36)  NULL,
    version       INT          NOT NULL,
    name          VARCHAR(128) NOT NULL,
    effectivefrom DATE         NOT NULL,
    effectiveto   DATE         NULL,            -- inclusive; NULL = open-ended
    source        VARCHAR(512) NULL,            -- contract / handbook this version was read from
    verified      TINYINT(1)   NOT NULL DEFAULT 0,  -- 0 = placeholder, not yet checked against source
    notes         TEXT         NULL,
    added         DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_rulesets_family_version (family, version),
    KEY ix_rulesets_lookup (state, brokerid, effectivefrom),
    CONSTRAINT fk_rulesets_broker FOREIGN KEY (brokerid) REFERENCES brokers (recordid),
    CONSTRAINT ck_rulesets_dates CHECK (effectiveto IS NULL OR effectiveto >= effectivefrom)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One thing a rule set demands.
--   kind = credential   the subject must hold a covering credential of credentialtypeid
--   kind = vehicleage   params {"maxyears": 10}: pickup year - model year may not exceed maxyears
-- servicelevels: JSON array (["wheelchair","stretcher"]) limiting where it applies; NULL = all trips.
CREATE TABLE IF NOT EXISTS requirements (
    recordid         VARCHAR(36)  NOT NULL,
    rulesetid        VARCHAR(36)  NOT NULL,
    code             VARCHAR(64)  NOT NULL,     -- stable name for reports, e.g. DRIVER_CPR
    kind             VARCHAR(16)  NOT NULL,
    subject          VARCHAR(8)   NOT NULL,
    credentialtypeid VARCHAR(36)  NULL,
    maxagedays       INT          NULL,         -- overrides credentialtypes.maxagedays when set
    gracedays        INT          NOT NULL DEFAULT 0,
    servicelevels    LONGTEXT     NULL CHECK (servicelevels IS NULL OR JSON_VALID(servicelevels)),
    params           LONGTEXT     NULL CHECK (params IS NULL OR JSON_VALID(params)),
    description      VARCHAR(512) NOT NULL,
    citation         VARCHAR(512) NULL,         -- section / page within rulesets.source
    added            DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_requirements_ruleset_code (rulesetid, code),
    CONSTRAINT fk_requirements_ruleset FOREIGN KEY (rulesetid) REFERENCES rulesets (recordid),
    CONSTRAINT fk_requirements_type FOREIGN KEY (credentialtypeid) REFERENCES credentialtypes (recordid),
    CONSTRAINT ck_requirements_kind CHECK (kind IN ('credential','vehicleage')),
    CONSTRAINT ck_requirements_subject CHECK (subject IN ('driver','vehicle','company')),
    CONSTRAINT ck_requirements_credential CHECK (kind <> 'credential' OR credentialtypeid IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ================================================================================================
-- TENANTS
-- ================================================================================================

CREATE TABLE IF NOT EXISTS accounts (
    recordid    VARCHAR(36)  NOT NULL,
    name        VARCHAR(128) NOT NULL,
    state       CHAR(2)      NOT NULL DEFAULT 'FL',
    timezone    VARCHAR(64)  NOT NULL DEFAULT 'America/New_York',
    npi         VARCHAR(16)  NULL,
    medicaidid  VARCHAR(32)  NULL,
    added       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated     DATETIME     NULL,
    deleted     DATETIME     NULL,
    PRIMARY KEY (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS users (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    email        VARCHAR(255) NOT NULL,
    name         VARCHAR(128) NOT NULL,
    passwordhash VARCHAR(255) NOT NULL,
    role         VARCHAR(12)  NOT NULL DEFAULT 'staff',   -- owner | admin | staff | auditor
    lastlogin    DATETIME     NULL,
    added        DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated      DATETIME     NULL,
    deleted      DATETIME     NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_users_email (email),
    KEY ix_users_account (accountid),
    CONSTRAINT fk_users_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT ck_users_role CHECK (role IN ('owner','admin','staff','auditor'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ================================================================================================
-- THE VAULT - drivers, vehicles, the files that prove things about them, and the credentials read
-- from those files.
-- ================================================================================================

-- externalid is the dispatch system's ID for the driver; trip imports match on it first, then on
-- exact name. Drivers first seen in a trip import are created as stubs (no credentials), so their
-- trips show up as exposure rather than disappearing.
CREATE TABLE IF NOT EXISTS drivers (
    recordid      VARCHAR(36)  NOT NULL,
    accountid     VARCHAR(36)  NOT NULL,
    externalid    VARCHAR(64)  NULL,
    firstname     VARCHAR(64)  NOT NULL,
    lastname      VARCHAR(64)  NOT NULL,
    licensenumber VARCHAR(32)  NULL,
    licensestate  CHAR(2)      NULL,
    email         VARCHAR(255) NULL,
    phone         VARCHAR(32)  NULL,
    hiredon       DATE         NULL,
    terminatedon  DATE         NULL,
    stub          TINYINT(1)   NOT NULL DEFAULT 0,   -- 1 = created by a trip import, never completed
    added         DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated       DATETIME     NULL,
    deleted       DATETIME     NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_drivers_external (accountid, externalid),
    KEY ix_drivers_name (accountid, lastname, firstname),
    CONSTRAINT fk_drivers_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vehicles (
    recordid      VARCHAR(36)  NOT NULL,
    accountid     VARCHAR(36)  NOT NULL,
    externalid    VARCHAR(64)  NULL,             -- dispatch unit number
    vin           VARCHAR(17)  NULL,
    plate         VARCHAR(16)  NULL,
    make          VARCHAR(32)  NULL,
    model         VARCHAR(32)  NULL,
    modelyear     SMALLINT     NULL,
    servicelevels LONGTEXT     NULL CHECK (servicelevels IS NULL OR JSON_VALID(servicelevels)),
    stub          TINYINT(1)   NOT NULL DEFAULT 0,
    added         DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated       DATETIME     NULL,
    deleted       DATETIME     NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_vehicles_external (accountid, externalid),
    UNIQUE KEY ux_vehicles_vin (accountid, vin),
    CONSTRAINT fk_vehicles_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- A stored file. The bytes live encrypted in object storage under storagekey; sha256 is of the
-- plaintext, so the same card uploaded twice is recognised and stored once per account.
CREATE TABLE IF NOT EXISTS documents (
    recordid    VARCHAR(36)  NOT NULL,
    accountid   VARCHAR(36)  NOT NULL,
    filename    VARCHAR(255) NOT NULL,
    mimetype    VARCHAR(128) NOT NULL,
    bytes       BIGINT       NOT NULL,
    sha256      CHAR(64)     NOT NULL,
    storagekey  VARCHAR(255) NOT NULL,
    uploadedby  VARCHAR(36)  NULL,
    added       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    deleted     DATETIME     NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_documents_hash (accountid, sha256),
    CONSTRAINT fk_documents_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One credential as printed: a CPR card, a background check result, an insurance COI.
--
-- Never overwritten. A renewal is a new row whose `supersedes` points at the old one; the old row
-- keeps covering the trips it covered. A revocation stamps revokedon and ends coverage from that
-- moment - trips run before it still count as covered.
--
-- The window a check actually uses is computed per requirement (see api/app/validity.py):
--   start = issuedon 00:00
--   end   = the earliest of  expireson + 1 day,  issuedon + maxagedays,  revokedon
--           (then + the requirement's gracedays, except after a revocation)
-- subjectid is drivers.recordid, vehicles.recordid, or accounts.recordid according to subject.
CREATE TABLE IF NOT EXISTS credentials (
    recordid         VARCHAR(36)  NOT NULL,
    accountid        VARCHAR(36)  NOT NULL,
    credentialtypeid VARCHAR(36)  NOT NULL,
    subject          VARCHAR(8)   NOT NULL,
    subjectid        VARCHAR(36)  NOT NULL,
    documentid       VARCHAR(36)  NULL,
    number           VARCHAR(64)  NULL,
    issuer           VARCHAR(128) NULL,
    issuedon         DATE         NOT NULL,
    expireson        DATE         NULL,          -- NULL = nothing printed; maxagedays may still apply
    revokedon        DATETIME     NULL,
    revokereason     VARCHAR(255) NULL,
    supersedes       VARCHAR(36)  NULL,
    verifiedby       VARCHAR(36)  NULL,
    verifiedon       DATETIME     NULL,
    notes            VARCHAR(512) NULL,
    enteredby        VARCHAR(36)  NULL,
    added            DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated          DATETIME     NULL,
    deleted          DATETIME     NULL,          -- data-entry mistakes only; renewals never delete
    PRIMARY KEY (recordid),
    KEY ix_credentials_subject (accountid, subject, subjectid, credentialtypeid, issuedon),
    CONSTRAINT fk_credentials_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_credentials_type FOREIGN KEY (credentialtypeid) REFERENCES credentialtypes (recordid),
    CONSTRAINT fk_credentials_document FOREIGN KEY (documentid) REFERENCES documents (recordid),
    CONSTRAINT fk_credentials_supersedes FOREIGN KEY (supersedes) REFERENCES credentials (recordid),
    CONSTRAINT ck_credentials_subject CHECK (subject IN ('driver','vehicle','company')),
    CONSTRAINT ck_credentials_dates CHECK (expireson IS NULL OR expireson >= issuedon)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ================================================================================================
-- PHI - the only table holding protected health information. `payload` is AES-256-GCM ciphertext
-- (base64 of nonce || ciphertext || tag) of a JSON object; `keyversion` names the key that sealed
-- it so keys can be rotated. The owner row (a trip, a leg, or an import batch) is named by
-- ownertype + ownerid.
-- ================================================================================================

CREATE TABLE IF NOT EXISTS phi (
    recordid    VARCHAR(36)  NOT NULL,
    accountid   VARCHAR(36)  NOT NULL,
    ownertype   VARCHAR(8)   NOT NULL,          -- trip | leg | batch
    ownerid     VARCHAR(36)  NOT NULL,
    keyversion  SMALLINT     NOT NULL,
    payload     LONGTEXT     NOT NULL,
    added       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_phi_owner (ownertype, ownerid),
    KEY ix_phi_account (accountid),
    CONSTRAINT fk_phi_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT ck_phi_owner CHECK (ownertype IN ('trip','leg','batch'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ================================================================================================
-- THE TRIP LEDGER
-- ================================================================================================

-- One uploaded dispatch export. Same staged → accepted | rejected lifecycle as driverimports: the
-- parsed rows are sealed into `phi` (ownertype = batch) at upload, the user reviews the preview,
-- and accepting writes exactly what was shown. The same file can never be imported twice.
CREATE TABLE IF NOT EXISTS importbatches (
    recordid    VARCHAR(36)  NOT NULL,
    accountid   VARCHAR(36)  NOT NULL,
    userid      VARCHAR(36)  NULL,
    filename    VARCHAR(255) NOT NULL,
    sha256      CHAR(64)     NOT NULL,
    source      VARCHAR(16)  NOT NULL DEFAULT 'csv',
    status      VARCHAR(12)  NOT NULL DEFAULT 'staged',   -- staged | accepted | rejected
    rowcount    INT          NOT NULL DEFAULT 0,
    tripcount   INT          NOT NULL DEFAULT 0,
    mapping     LONGTEXT     NULL CHECK (mapping IS NULL OR JSON_VALID(mapping)),
    errors      LONGTEXT     NULL CHECK (errors IS NULL OR JSON_VALID(errors)),
    added       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    decidedon   DATETIME     NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_importbatches_hash (accountid, sha256),
    CONSTRAINT fk_importbatches_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT ck_importbatches_status CHECK (status IN ('staged','accepted','rejected'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- A billable trip. lastrunid points at the evaluation run whose checks are current for it.
CREATE TABLE IF NOT EXISTS trips (
    recordid      VARCHAR(36)   NOT NULL,
    accountid     VARCHAR(36)   NOT NULL,
    batchid       VARCHAR(36)   NULL,
    externalid    VARCHAR(64)   NOT NULL,       -- dispatch / broker trip number
    brokerid      VARCHAR(36)   NULL,
    tripdate      DATE          NOT NULL,
    servicelevel  VARCHAR(16)   NULL,           -- ambulatory | wheelchair | stretcher | ...
    billedamount  DECIMAL(10,2) NOT NULL DEFAULT 0,
    billingstatus VARCHAR(12)   NOT NULL DEFAULT 'unbilled',   -- unbilled | billed | paid | held
    lastrunid     VARCHAR(36)   NULL,
    added         DATETIME      NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated       DATETIME      NULL,
    deleted       DATETIME      NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_trips_external (accountid, externalid),
    KEY ix_trips_date (accountid, tripdate),
    KEY ix_trips_run (lastrunid),
    CONSTRAINT fk_trips_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_trips_batch FOREIGN KEY (batchid) REFERENCES importbatches (recordid),
    CONSTRAINT fk_trips_broker FOREIGN KEY (brokerid) REFERENCES brokers (recordid),
    CONSTRAINT ck_trips_billing CHECK (billingstatus IN ('unbilled','billed','paid','held'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One leg of a trip. Compliance is judged per leg, because a driver or vehicle swap mid-trip means
-- different people and equipment must each be covered. pickupat is the instant every check is
-- measured against (local wall clock). Addresses, GPS and the raw import row are in `phi`.
CREATE TABLE IF NOT EXISTS triplegs (
    recordid        VARCHAR(36)  NOT NULL,
    accountid       VARCHAR(36)  NOT NULL,
    tripid          VARCHAR(36)  NOT NULL,
    legnumber       SMALLINT     NOT NULL DEFAULT 1,
    driverid        VARCHAR(36)  NULL,
    vehicleid       VARCHAR(36)  NULL,
    driverexternal  VARCHAR(128) NULL,          -- as it appeared in the export
    vehicleexternal VARCHAR(128) NULL,
    pickupat        DATETIME     NOT NULL,
    dropoffat       DATETIME     NULL,
    signature       TINYINT(1)   NOT NULL DEFAULT 0,   -- member signature captured
    gps             TINYINT(1)   NOT NULL DEFAULT 0,   -- GPS pickup/drop-off captured
    added           DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_triplegs_trip (tripid, legnumber),
    KEY ix_triplegs_driver (accountid, driverid, pickupat),
    KEY ix_triplegs_vehicle (accountid, vehicleid, pickupat),
    CONSTRAINT fk_triplegs_trip FOREIGN KEY (tripid) REFERENCES trips (recordid),
    CONSTRAINT fk_triplegs_driver FOREIGN KEY (driverid) REFERENCES drivers (recordid),
    CONSTRAINT fk_triplegs_vehicle FOREIGN KEY (vehicleid) REFERENCES vehicles (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ================================================================================================
-- CHECKS - every answer is saved with the run that produced it, so any past answer can be shown to
-- an auditor exactly as it was given.
-- ================================================================================================

-- rulesnapshot is the requirement rows the run used, frozen as JSON; engineversion names the
-- evaluator code. Together with the credential rows (never overwritten) they reproduce the run.
CREATE TABLE IF NOT EXISTS evaluationruns (
    recordid      VARCHAR(36)  NOT NULL,
    accountid     VARCHAR(36)  NOT NULL,
    userid        VARCHAR(36)  NULL,
    reason        VARCHAR(32)  NOT NULL,        -- import | manual | credential-change
    engineversion VARCHAR(16)  NOT NULL,
    rulesnapshot  LONGTEXT     NOT NULL CHECK (JSON_VALID(rulesnapshot)),
    tripcount     INT          NOT NULL DEFAULT 0,
    legcount      INT          NOT NULL DEFAULT 0,
    failcount     INT          NOT NULL DEFAULT 0,
    started       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    finished      DATETIME     NULL,
    PRIMARY KEY (recordid),
    KEY ix_evaluationruns_account (accountid, started),
    CONSTRAINT fk_evaluationruns_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One saved result per (run, leg, requirement).
--   pass     a credential covered the pickup; credentialid + windowstart/windowend say which/when
--   fail     nothing covered it; reason says why (expired, revoked, over max age, none on file ...)
--   nosubject the leg has no matched driver/vehicle to check
CREATE TABLE IF NOT EXISTS legchecks (
    recordid      VARCHAR(36)  NOT NULL,
    runid         VARCHAR(36)  NOT NULL,
    accountid     VARCHAR(36)  NOT NULL,
    tripid        VARCHAR(36)  NOT NULL,
    legid         VARCHAR(36)  NOT NULL,
    requirementid VARCHAR(36)  NOT NULL,
    subject       VARCHAR(8)   NOT NULL,
    subjectid     VARCHAR(36)  NULL,
    outcome       VARCHAR(10)  NOT NULL,
    reasoncode    VARCHAR(24)  NULL,            -- expired | revoked | maxage | missing | notyet | toold | nosubject | nomodelyear
    reason        VARCHAR(255) NULL,
    credentialid  VARCHAR(36)  NULL,
    windowstart   DATETIME     NULL,
    windowend     DATETIME     NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_legchecks (runid, legid, requirementid),
    KEY ix_legchecks_trip (tripid, runid),
    KEY ix_legchecks_outcome (accountid, runid, outcome),
    CONSTRAINT fk_legchecks_run FOREIGN KEY (runid) REFERENCES evaluationruns (recordid),
    CONSTRAINT fk_legchecks_leg FOREIGN KEY (legid) REFERENCES triplegs (recordid),
    CONSTRAINT fk_legchecks_requirement FOREIGN KEY (requirementid) REFERENCES requirements (recordid),
    CONSTRAINT ck_legchecks_outcome CHECK (outcome IN ('pass','fail','nosubject'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ================================================================================================
-- AUDITS
-- ================================================================================================

CREATE TABLE IF NOT EXISTS auditrequests (
    recordid    VARCHAR(36)  NOT NULL,
    accountid   VARCHAR(36)  NOT NULL,
    requester   VARCHAR(128) NOT NULL,          -- "MTM Program Integrity", "AHCA MPI", ...
    reference   VARCHAR(64)  NULL,              -- their case / letter number
    receivedon  DATE         NOT NULL,
    dueon       DATE         NULL,
    status      VARCHAR(12)  NOT NULL DEFAULT 'open',     -- open | submitted | closed
    notes       TEXT         NULL,
    createdby   VARCHAR(36)  NULL,
    added       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated     DATETIME     NULL,
    PRIMARY KEY (recordid),
    CONSTRAINT fk_auditrequests_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- A generated bundle. Tied to one evaluation run so the packet always matches the checks that were
-- saved; sha256 is of the zip as delivered, so a copy in the auditor's hands can be verified.
CREATE TABLE IF NOT EXISTS auditpackets (
    recordid       VARCHAR(36)  NOT NULL,
    accountid      VARCHAR(36)  NOT NULL,
    auditrequestid VARCHAR(36)  NULL,
    runid          VARCHAR(36)  NOT NULL,
    tripcount      INT          NOT NULL,
    sha256         CHAR(64)     NOT NULL,
    storagekey     VARCHAR(255) NOT NULL,
    bytes          BIGINT       NOT NULL,
    generatedby    VARCHAR(36)  NULL,
    added          DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (recordid),
    CONSTRAINT fk_auditpackets_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_auditpackets_request FOREIGN KEY (auditrequestid) REFERENCES auditrequests (recordid),
    CONSTRAINT fk_auditpackets_run FOREIGN KEY (runid) REFERENCES evaluationruns (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS auditpackettrips (
    packetid    VARCHAR(36)  NOT NULL,
    tripid      VARCHAR(36)  NOT NULL,
    PRIMARY KEY (packetid, tripid),
    CONSTRAINT fk_auditpackettrips_packet FOREIGN KEY (packetid) REFERENCES auditpackets (recordid),
    CONSTRAINT fk_auditpackettrips_trip FOREIGN KEY (tripid) REFERENCES trips (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ================================================================================================
-- ACTIVITY LOG - every view of PHI, every change, every export (HIPAA access logging). Append-only:
-- the triggers below refuse updates and deletes.
-- ================================================================================================

CREATE TABLE IF NOT EXISTS activitylog (
    recordid    VARCHAR(36)  NOT NULL,
    accountid   VARCHAR(36)  NULL,
    userid      VARCHAR(36)  NULL,
    action      VARCHAR(32)  NOT NULL,          -- view | create | update | delete | export | login ...
    entitytype  VARCHAR(32)  NULL,
    entityid    VARCHAR(36)  NULL,
    phi         TINYINT(1)   NOT NULL DEFAULT 0,  -- 1 = this action exposed PHI
    detail      LONGTEXT     NULL CHECK (detail IS NULL OR JSON_VALID(detail)),
    ip          VARCHAR(45)  NULL,
    added       DATETIME(3)  NOT NULL DEFAULT UTC_TIMESTAMP(3),
    PRIMARY KEY (recordid),
    KEY ix_activitylog_account (accountid, added),
    KEY ix_activitylog_entity (entitytype, entityid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ================================================================================================
-- EXPOSURE - trips whose current checks contain a failure, with the dollars billed on them.
-- ================================================================================================

-- INVOKER, not the default DEFINER: a view that remembers its creator stops working the moment the
-- database is moved to a machine where that login does not exist.
CREATE OR REPLACE SQL SECURITY INVOKER VIEW tripexposure AS
SELECT t.accountid,
       t.recordid      AS tripid,
       t.externalid,
       t.tripdate,
       t.brokerid,
       t.billedamount,
       t.billingstatus,
       t.lastrunid     AS runid,
       COUNT(*)        AS failures
FROM trips t
JOIN legchecks c ON c.tripid = t.recordid AND c.runid = t.lastrunid
WHERE t.deleted IS NULL
  AND c.outcome IN ('fail','nosubject')
GROUP BY t.accountid, t.recordid, t.externalid, t.tripdate, t.brokerid, t.billedamount,
         t.billingstatus, t.lastrunid;

-- ================================================================================================
-- TRIGGERS
-- ================================================================================================

DELIMITER $$

-- Two versions of one rule-set family may not cover the same day. (PostgreSQL would do this with an
-- exclusion constraint; MariaDB needs a trigger.)
CREATE OR REPLACE TRIGGER tr_rulesets_nooverlap_ins BEFORE INSERT ON rulesets FOR EACH ROW
BEGIN
    IF EXISTS (SELECT 1 FROM rulesets r
               WHERE r.family = NEW.family
                 AND r.effectivefrom <= COALESCE(NEW.effectiveto, '9999-12-31')
                 AND COALESCE(r.effectiveto, '9999-12-31') >= NEW.effectivefrom) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'rulesets: overlapping versions in one family';
    END IF;
END$$

CREATE OR REPLACE TRIGGER tr_rulesets_nooverlap_upd BEFORE UPDATE ON rulesets FOR EACH ROW
BEGIN
    IF EXISTS (SELECT 1 FROM rulesets r
               WHERE r.family = NEW.family
                 AND r.recordid <> NEW.recordid
                 AND r.effectivefrom <= COALESCE(NEW.effectiveto, '9999-12-31')
                 AND COALESCE(r.effectiveto, '9999-12-31') >= NEW.effectivefrom) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'rulesets: overlapping versions in one family';
    END IF;
END$$

CREATE OR REPLACE TRIGGER tr_activitylog_noupdate BEFORE UPDATE ON activitylog FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'activitylog is append-only';
END$$

CREATE OR REPLACE TRIGGER tr_activitylog_nodelete BEFORE DELETE ON activitylog FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'activitylog is append-only';
END$$

-- Saved checks are evidence; they are never edited after the run writes them.
CREATE OR REPLACE TRIGGER tr_legchecks_noupdate BEFORE UPDATE ON legchecks FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'legchecks are immutable';
END$$

DELIMITER ;
