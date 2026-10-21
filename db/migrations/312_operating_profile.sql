-- ################################################################################################
-- # 312 - the company's operating profile, as records rather than loose answers.
-- #
-- # What a driver owes depends on what the company does: where it operates, which programs it
-- # carries, which broker contracts it holds, how it engages drivers, and whether its operation is
-- # an FDOT Chapter 14-90 bus transit system. Those were yes/no answers with no dates and no history.
-- # They are records now, each with its own dates, and every change to the profile is kept.
-- #
-- # Unknown is not exempt. A 14-90 determination left at "needs review" reaches the engine as
-- # unknown, and every rule that depends on it says so instead of quietly not applying.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS companyprofiles (
  accountid          VARCHAR(36)  NOT NULL PRIMARY KEY,
  operatingstates    VARCHAR(255) NULL,      -- comma separated, e.g. FL,GA
  employmentmodel    VARCHAR(16)  NULL,      -- employee | contractor | mixed
  fdot1490           VARCHAR(16)  NULL,      -- covered | notcovered | review
  compliancecontact  VARCHAR(36)  NULL,      -- a user
  updated            DATETIME     NULL,
  updatedby          VARCHAR(36)  NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Every saved version of the profile, never rewritten.
CREATE TABLE IF NOT EXISTS companyprofilehistory (
  recordid   VARCHAR(36) NOT NULL PRIMARY KEY,
  accountid  VARCHAR(36) NOT NULL,
  snapshot   JSON        NOT NULL,
  savedon    DATETIME    NOT NULL,
  savedby    VARCHAR(36) NULL,
  KEY ix_companyprofilehistory (accountid, savedon)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS companyprograms (
  recordid      VARCHAR(36) NOT NULL PRIMARY KEY,
  accountid     VARCHAR(36) NOT NULL,
  -- privatepay | medicaid | medicareadvantage | commercialinsurance | workerscomp | facility
  program       VARCHAR(24) NOT NULL,
  state         CHAR(2)     NULL,
  status        VARCHAR(12) NOT NULL DEFAULT 'active',   -- active | planned | ended
  effectivefrom DATE        NULL,
  effectiveto   DATE        NULL,
  added         DATETIME    NOT NULL,
  addedby       VARCHAR(36) NULL,
  KEY ix_companyprograms (accountid, program)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS companycontracts (
  recordid      VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid     VARCHAR(36)  NOT NULL,
  broker        VARCHAR(64)  NOT NULL,
  state         CHAR(2)      NULL,
  contractref   VARCHAR(64)  NULL,
  program       VARCHAR(24)  NULL,
  services      VARCHAR(128) NULL,       -- comma separated: ambulatory, wheelchair, stretcher
  effectivefrom DATE         NULL,
  effectiveto   DATE         NULL,
  -- Whether anybody has read the contract for its driver requirements. Unread is not "none".
  reviewed      TINYINT(1)   NOT NULL DEFAULT 0,
  reviewedby    VARCHAR(36)  NULL,
  reviewedon    DATETIME     NULL,
  documentid    VARCHAR(36)  NULL,
  note          VARCHAR(512) NULL,
  added         DATETIME     NOT NULL,
  addedby       VARCHAR(36)  NULL,
  KEY ix_companycontracts (accountid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- FMCSA coverage and CDL licensing are separate questions, and so is Chapter 14-90. Each vehicle
-- carries its own determination; blank means nobody has decided, not that it is exempt.
CREATE TABLE IF NOT EXISTS vehicleassessments (
  vehicleid   VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid   VARCHAR(36)  NOT NULL,
  fmcsa       VARCHAR(12)  NULL,     -- covered | notcovered | review
  fdot1490    VARCHAR(12)  NULL,     -- covered | notcovered | review
  note        VARCHAR(512) NULL,
  assessedby  VARCHAR(36)  NULL,
  assessedon  DATETIME     NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- How the company engages this driver. Blank falls back to the company's employment model.
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS engagement VARCHAR(16) NULL AFTER status;
  -- employee | contractor | subcontracted

-- The I-9 and the W-4 are employee paperwork. A contractor has neither, and where nobody has said
-- how the driver is engaged the rule says so instead of guessing.
UPDATE compliancerules SET applieswhen = '{"fact":"driver.employee","is":true}'
 WHERE subject = 'driver' AND accountid IS NULL AND code IN ('I9', 'W4') AND effectiveto IS NULL;

-- The license copy is the Medicaid source of the license qualification; the FMCSA source is its
-- own rule now, so this one names only what is its own.
UPDATE compliancerules SET authority = 'CMS', citation = '42 U.S.C. 1396a(a)(87)(B)'
 WHERE subject = 'driver' AND accountid IS NULL AND code = 'DRIVER_LICENSE_COPY' AND effectiveto IS NULL;

-- Which program a rule belongs to. The Medicaid rules count toward a driver's Medicaid
-- qualification; everything else is general and counts toward every program.
UPDATE compliancerules SET program = 'medicaid'
 WHERE subject = 'driver' AND accountid IS NULL AND effectiveto IS NULL
   AND authoritycategory IN ('FEDERAL_MEDICAID', 'STATE_MEDICAID');
