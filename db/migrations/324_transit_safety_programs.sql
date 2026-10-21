-- ################################################################################################
-- # 324 - transit safety programs, one determination each.
-- #
-- # "FDOT Chapter 14-90" was one Florida field on the company. Bus and paratransit safety regimes
-- # are not only Florida's: another state may run its own, and the FTA's Public Transportation
-- # Agency Safety Plan (49 CFR Part 673) reaches agencies on FTA funds anywhere. So the programs are
-- # rows in a catalog, the company determines each one that touches its states, and a driver is
-- # assigned to the programs they work under. Unknown is never exempt: an undetermined program
-- # leaves every rule that depends on it under review.
-- #
-- # Carried over: the company's 14-90 answer, and every driver ticked as working a 14-90 operation.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS transitsafetyprograms (
  code        VARCHAR(24)  NOT NULL PRIMARY KEY,
  state       CHAR(2)      NOT NULL,           -- US for a federal program
  name        VARCHAR(128) NOT NULL,
  authority   VARCHAR(64)  NOT NULL,
  citation    VARCHAR(128) NOT NULL,
  description VARCHAR(512) NULL,
  sortorder   INT          NOT NULL DEFAULT 0,
  active      TINYINT(1)   NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO transitsafetyprograms (code, state, name, authority, citation, description, sortorder) VALUES
  ('FL_1490', 'FL', 'Bus Transit System Safety', 'FDOT', 'F.A.C. Chapter 14-90',
   'Florida bus transit systems, including some private contract operators and paratransit vehicles (Rule 14-90.002).', 10),
  ('US_PTASP', 'US', 'Public Transportation Agency Safety Plan', 'FTA', '49 CFR Part 673',
   'Operators of public transportation that receive FTA Urbanized Area Formula (Section 5307) funds, and their contractors where the plan reaches them.', 1);

CREATE TABLE IF NOT EXISTS companytransitprograms (
  accountid     VARCHAR(36) NOT NULL,
  programcode   VARCHAR(24) NOT NULL,
  determination VARCHAR(12) NOT NULL,          -- covered | notcovered | review
  determinedon  DATETIME    NOT NULL,
  determinedby  VARCHAR(36) NULL,
  PRIMARY KEY (accountid, programcode)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS drivertransitprograms (
  accountid   VARCHAR(36) NOT NULL,
  driverid    VARCHAR(36) NOT NULL,
  programcode VARCHAR(24) NOT NULL,
  added       DATETIME    NOT NULL,
  PRIMARY KEY (driverid, programcode),
  KEY ix_drivertransitprograms (accountid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO companytransitprograms (accountid, programcode, determination, determinedon, determinedby)
SELECT accountid, 'FL_1490', fdot1490, COALESCE(updated, UTC_TIMESTAMP()), updatedby
FROM companyprofiles WHERE fdot1490 IN ('covered', 'notcovered', 'review');

INSERT IGNORE INTO drivertransitprograms (accountid, driverid, programcode, added)
SELECT accountid, recordid, 'FL_1490', UTC_TIMESTAMP()
FROM drivers WHERE chapter1490 = 1 AND deleted IS NULL;
