-- ################################################################################################
-- # 314 - rule versions, contract requirements, driver approvals, daily snapshots, enforcement.
-- #
-- # Rule versions: every rule as it stood, each time it changed. Captured by the application after
-- # every migration run and every review decision, so a check can say which version it read.
-- #
-- # Contract requirements: what a broker contract asks of drivers, as rows pointing at a catalog
-- # qualification, with the contract's own renewal. Each one is evaluated as one more source behind
-- # that qualification. A contract is tied to the payer its trips are billed to.
-- #
-- # Driver approvals: which contracts a driver has been approved to work. Where a contract requires
-- # approval, a driver without it cannot take that contract's trips.
-- #
-- # Snapshots: each driver's standing per program, once a day, kept - the file as it stood then.
-- #
-- # Enforcement: off until the company turns it on, and then only for rules a reviewer approved.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS compliancerulesversions (
  recordid    VARCHAR(36) NOT NULL PRIMARY KEY,
  rulecode    VARCHAR(64) NOT NULL,
  accountid   VARCHAR(36) NULL,
  version     INT         NOT NULL,
  snapshot    JSON        NOT NULL,
  snapshotsha CHAR(64)    NOT NULL,
  capturedon  DATETIME    NOT NULL,
  capturedby  VARCHAR(36) NULL,
  reason      VARCHAR(128) NULL,
  UNIQUE KEY ux_compliancerulesversions (rulecode, accountid, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE companycontracts
  ADD COLUMN IF NOT EXISTS payerid VARCHAR(36) NULL AFTER broker,
  ADD COLUMN IF NOT EXISTS requiresapproval TINYINT(1) NOT NULL DEFAULT 0 AFTER services;

CREATE TABLE IF NOT EXISTS contractrequirements (
  recordid          VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid         VARCHAR(36)  NOT NULL,
  contractid        VARCHAR(36)  NOT NULL,
  qualificationcode VARCHAR(16)  NOT NULL,
  renewaldays       INT          NULL,      -- NULL: once, as the contract does not say otherwise
  clause            VARCHAR(128) NULL,      -- where in the contract it is asked
  note              VARCHAR(512) NULL,
  added             DATETIME     NOT NULL,
  addedby           VARCHAR(36)  NULL,
  endedon           DATETIME     NULL,
  KEY ix_contractrequirements (accountid, contractid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS driverauthorizations (
  recordid    VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid   VARCHAR(36)  NOT NULL,
  driverid    VARCHAR(36)  NOT NULL,
  contractid  VARCHAR(36)  NOT NULL,
  approvedon  DATETIME     NOT NULL,
  approvedby  VARCHAR(36)  NULL,
  endedon     DATETIME     NULL,
  endedby     VARCHAR(36)  NULL,
  KEY ix_driverauthorizations (accountid, driverid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS programqualificationsnapshots (
  recordid   VARCHAR(36) NOT NULL PRIMARY KEY,
  accountid  VARCHAR(36) NOT NULL,
  driverid   VARCHAR(36) NOT NULL,
  program    VARCHAR(24) NOT NULL,
  status     VARCHAR(24) NOT NULL,
  reasons    JSON        NULL,
  takenon    DATE        NOT NULL,
  takenat    DATETIME    NOT NULL,
  UNIQUE KEY ux_programsnapshots (accountid, driverid, program, takenon)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE companyprofiles
  ADD COLUMN IF NOT EXISTS enforcetripcheck TINYINT(1) NOT NULL DEFAULT 0 AFTER compliancecontact;

-- The Florida rules reach a company operating in Florida, not only one headquartered there.
UPDATE compliancerules
   SET applieswhen = REPLACE(applieswhen, '{"fact":"company.state","eq":"FL"}',
       '{"any":[{"fact":"company.state","eq":"FL"},{"fact":"company.operatingstates","has":"FL"}]}')
 WHERE subject = 'driver' AND accountid IS NULL AND effectiveto IS NULL
   AND applieswhen LIKE '%"company.state","eq":"FL"%';
