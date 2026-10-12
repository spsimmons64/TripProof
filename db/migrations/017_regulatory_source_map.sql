-- ################################################################################################
-- # 017 - the regulatory source map: where the law lives, how it is watched, and how rules apply.
-- #
-- # jurisdictions    'US' and each state (and localities later): its official directory link, the
-- #                  search terms used to find rules there, and when its source map was last built.
-- # regsources       the registry of authoritative places - legislature, administrative code, DOT,
-- #                  DMV/DPS, utility commission, health agency, licensing, insurance regulator, local
-- #                  government, federal agencies - each with its source type and how it is monitored
-- #                  (eCFR API, Federal Register API, RSS, page fingerprint, or manual review on a
-- #                  schedule). Cited documents (sources) belong to one; so does every rule through them.
-- # regchanges       what monitoring detected: a review queue, with the rules and accounts it may affect.
-- # requirements     + required status (REQUIRED / CONDITIONAL / NO_REQUIREMENT_FOUND), structured
-- #                  triggers (machine-checkable applicability against the company profile), the legal
-- #                  citation apart from the URL, source type, authority, effective/repeal dates, what
-- #                  was searched (for "no requirement found"), and review stamps.
-- # companyprofiles  how each customer operates (interstate?, vehicles and designed capacity,
-- #                  services, employees, …) - what conditional rules are evaluated against.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS jurisdictions (
    code          VARCHAR(8)    NOT NULL,           -- 'US', 'FL', …
    name          VARCHAR(64)   NOT NULL,
    level         VARCHAR(8)    NOT NULL,           -- federal | state
    directoryurl  VARCHAR(512)  NULL,               -- official directory entry (e.g. USA.gov) used to find its sites
    searchterms   LONGTEXT      NULL CHECK (searchterms IS NULL OR JSON_VALID(searchterms)),
    mappedon      DATE          NULL,               -- when its source map was last completed
    mappedby      VARCHAR(36)   NULL,
    notes         TEXT          NULL,
    added         DATETIME      NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated       DATETIME      NULL,
    PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS regsources (
    recordid           VARCHAR(36)   NOT NULL,
    jurisdiction       VARCHAR(8)    NOT NULL,       -- 'US' or a state
    locality           VARCHAR(64)   NULL,           -- county/city for local sources
    category           VARCHAR(20)   NOT NULL,       -- legislature | admincode | register | dot | dmv | psc | health |
                                                     -- licensing | insurance | labor | business | local | federalagency | directory
    sourcetype         VARCHAR(20)   NOT NULL,       -- PRIMARY_STATUTE | PRIMARY_REGULATION | GOVERNMENT_GUIDANCE |
                                                     -- AGENCY_POLICY | LOCAL_ORDINANCE | DIRECTORY | MEDICAID | MCO | BROKER | CONTRACT
    name               VARCHAR(255)  NOT NULL,
    agency             VARCHAR(128)  NULL,
    url                VARCHAR(512)  NOT NULL,
    citationprefix     VARCHAR(32)   NULL,           -- '49 CFR', 'F.S.', 'F.A.C.' …
    monitormethod      VARCHAR(20)   NOT NULL DEFAULT 'manual',  -- ecfr | federalregister | rss | pagehash | manual
    monitortarget      VARCHAR(512)  NULL,           -- e.g. 'title=49&part=383', an FR agency slug, a feed URL
    checkeverydays     INT           NOT NULL DEFAULT 30,
    lastcheckedon      DATETIME      NULL,
    lastchangedon      DATE          NULL,
    lastfingerprint    VARCHAR(128)  NULL,
    lastcheckstatus    VARCHAR(255)  NULL,
    active             TINYINT(1)    NOT NULL DEFAULT 1,
    notes              TEXT          NULL,
    added              DATETIME      NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated            DATETIME      NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_regsources_url (jurisdiction, url(255)),
    KEY ix_regsources_juris (jurisdiction, category),
    CONSTRAINT ck_regsources_type CHECK (sourcetype IN ('PRIMARY_STATUTE','PRIMARY_REGULATION','GOVERNMENT_GUIDANCE',
        'AGENCY_POLICY','LOCAL_ORDINANCE','DIRECTORY','MEDICAID','MCO','BROKER','CONTRACT')),
    CONSTRAINT ck_regsources_monitor CHECK (monitormethod IN ('ecfr','federalregister','rss','pagehash','manual'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS regchanges (
    recordid      VARCHAR(36)   NOT NULL,
    regsourceid   VARCHAR(36)   NOT NULL,
    detectedon    DATETIME      NOT NULL DEFAULT UTC_TIMESTAMP(),
    kind          VARCHAR(16)   NOT NULL,            -- amended | published | changed | due
    title         VARCHAR(512)  NOT NULL,
    url           VARCHAR(512)  NULL,
    effectiveon   DATE          NULL,
    detail        TEXT          NULL,
    externalid    VARCHAR(128)  NULL,                -- FR document number, feed item id … (dedupe)
    status        VARCHAR(10)   NOT NULL DEFAULT 'new',   -- new | reviewed | dismissed
    reviewedby    VARCHAR(36)   NULL,
    reviewedon    DATETIME      NULL,
    reviewnote    TEXT          NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_regchanges_ext (regsourceid, externalid),
    KEY ix_regchanges_status (status, detectedon),
    CONSTRAINT fk_regchanges_source FOREIGN KEY (regsourceid) REFERENCES regsources (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE sources ADD COLUMN IF NOT EXISTS regsourceid VARCHAR(36) NULL AFTER recordid;

ALTER TABLE requirements
    ADD COLUMN IF NOT EXISTS status         VARCHAR(24)  NOT NULL DEFAULT 'REQUIRED' AFTER kind,
    ADD COLUMN IF NOT EXISTS triggers       LONGTEXT     NULL CHECK (triggers IS NULL OR JSON_VALID(triggers)) AFTER applieswhen,
    ADD COLUMN IF NOT EXISTS triggersource  VARCHAR(8)   NULL AFTER triggers,     -- auto | manual
    ADD COLUMN IF NOT EXISTS exceptions     TEXT         NULL AFTER triggersource,
    ADD COLUMN IF NOT EXISTS legalcitation  VARCHAR(128) NULL AFTER citation,     -- '49 CFR 383.93' - durable, unlike a URL
    ADD COLUMN IF NOT EXISTS sourcetype     VARCHAR(20)  NULL AFTER legalcitation,
    ADD COLUMN IF NOT EXISTS authorityname  VARCHAR(128) NULL AFTER authority,
    ADD COLUMN IF NOT EXISTS effectiveon    DATE         NULL AFTER sourceurl,
    ADD COLUMN IF NOT EXISTS repealedon     DATE         NULL AFTER effectiveon,
    ADD COLUMN IF NOT EXISTS searched       LONGTEXT     NULL CHECK (searched IS NULL OR JSON_VALID(searched)) AFTER repealedon,
    ADD COLUMN IF NOT EXISTS lastreviewedon DATE         NULL AFTER searched,
    ADD COLUMN IF NOT EXISTS reviewedby     VARCHAR(36)  NULL AFTER lastreviewedon,
    ADD COLUMN IF NOT EXISTS lastchangedon  DATE         NULL AFTER reviewedby;

ALTER TABLE requirements
    ADD CONSTRAINT IF NOT EXISTS ck_requirements_status CHECK (status IN ('REQUIRED','CONDITIONAL','NO_REQUIREMENT_FOUND'));

CREATE TABLE IF NOT EXISTS companyprofiles (
    accountid             VARCHAR(36)  NOT NULL,
    interstate            VARCHAR(8)   NULL,          -- no | yes | unsure
    forhire               TINYINT(1)   NULL,
    vehicletypes          LONGTEXT     NULL CHECK (vehicletypes IS NULL OR JSON_VALID(vehicletypes)),
    maxcapacity           INT          NULL,          -- largest manufacturer-designed seating, including the driver
    maxgvwr               INT          NULL,          -- heaviest vehicle GVWR (lbs)
    services              LONGTEXT     NULL CHECK (services IS NULL OR JSON_VALID(services)),
    employees             INT          NULL,
    entitytype            VARCHAR(16)  NULL,          -- llc | corporation | partnership | sole
    formedinstate         TINYINT(1)   NULL,
    fictitiousname        TINYINT(1)   NULL,
    publiccontracts       TINYINT(1)   NULL,
    occupationalexposure  TINYINT(1)   NULL,          -- staff reasonably expected to contact blood/OPIM
    backgroundreports     TINYINT(1)   NULL,          -- uses a consumer reporting agency for background checks
    updated               DATETIME     NULL,
    updatedby             VARCHAR(36)  NULL,
    PRIMARY KEY (accountid),
    CONSTRAINT fk_companyprofiles_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
