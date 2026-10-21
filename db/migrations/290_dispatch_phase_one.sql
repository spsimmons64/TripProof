-- Dispatch, phase one: the model. No screen changes with this file.
--
-- Three things the product could not say before, in the order they matter.
--
--   WHO WAS ON THIS LEG, AND WHO WAS ON IT BEFORE. `triplegs.driverid` is a column, so putting a
--   different driver on a trip overwrote the one who had it. For a product whose claim is that it
--   can prove who was qualified to drive a given trip, losing the original assignment is the one
--   loss that cannot be argued away afterwards. `tripassignments` keeps every one of them.
--
--   WHERE A TRIP HAS GOT TO, IN THE SIX WAYS IT CAN HAVE GOT ANYWHERE. One status column cannot
--   say that a trip is accepted by the broker, unassigned by dispatch, and not yet billable - all
--   of which are true at once the moment it arrives. Six columns, each with its own vocabulary.
--
--   WHAT WAS RETURNED TO A BROKER, AND WHETHER THEY EVER SAID SO. A rejected trip is not a deleted
--   trip. It stays the company's problem until the broker acknowledges it, because an unanswered
--   rejection that nobody is watching is a trip that simply does not get driven.
--
-- Every statement is guarded: DDL commits as it goes, so a file that fails halfway re-runs from
-- the top. MariaDB has no ADD CONSTRAINT IF NOT EXISTS, so each CHECK is dropped before it is
-- added - DROP CONSTRAINT IF EXISTS does work.

-- -----------------------------------------------------------------------------------------------
-- Where a trip has got to
-- -----------------------------------------------------------------------------------------------
-- On the TRIP, because they are true of the whole reservation: who it came from, whether dispatch
-- has covered it, and whether what came back may be billed.
ALTER TABLE trips ADD COLUMN IF NOT EXISTS brokerstate   VARCHAR(16) NOT NULL DEFAULT 'none';
ALTER TABLE trips ADD COLUMN IF NOT EXISTS dispatchstate VARCHAR(16) NOT NULL DEFAULT 'unassigned';
ALTER TABLE trips ADD COLUMN IF NOT EXISTS verifystate   VARCHAR(16) NOT NULL DEFAULT 'notready';

-- On the LEG, because they are not. A passenger can be delivered to their appointment while the
-- return leg has not been driven, and a trip that says "completed" in that state is lying.
ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS executionstate VARCHAR(16) NOT NULL DEFAULT 'scheduled';
ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS outcomestate   VARCHAR(16) NULL;

ALTER TABLE trips DROP CONSTRAINT IF EXISTS ck_trips_brokerstate;
ALTER TABLE trips ADD CONSTRAINT ck_trips_brokerstate CHECK (
  brokerstate IN ('none', 'offered', 'accepted', 'returnpending', 'returned'));
ALTER TABLE trips DROP CONSTRAINT IF EXISTS ck_trips_dispatchstate;
ALTER TABLE trips ADD CONSTRAINT ck_trips_dispatchstate CHECK (
  dispatchstate IN ('unassigned', 'assigned', 'needsreassign'));
ALTER TABLE trips DROP CONSTRAINT IF EXISTS ck_trips_verifystate;
ALTER TABLE trips ADD CONSTRAINT ck_trips_verifystate CHECK (
  verifystate IN ('notready', 'awaitingreview', 'verified', 'needscorrection'));
ALTER TABLE triplegs DROP CONSTRAINT IF EXISTS ck_triplegs_executionstate;
ALTER TABLE triplegs ADD CONSTRAINT ck_triplegs_executionstate CHECK (
  executionstate IN ('scheduled', 'enroute', 'arrived', 'onboard', 'completed'));
ALTER TABLE triplegs DROP CONSTRAINT IF EXISTS ck_triplegs_outcomestate;
ALTER TABLE triplegs ADD CONSTRAINT ck_triplegs_outcomestate CHECK (
  outcomestate IS NULL OR outcomestate IN ('cancelled', 'noshow', 'aborted', 'disputed'));

-- -----------------------------------------------------------------------------------------------
-- Who was on this leg
-- -----------------------------------------------------------------------------------------------
-- `triplegs.driverid` and `.vehicleid` stay, and stay authoritative - they are the assignment in
-- force, and the compliance engine reads them. This is the history behind them, written by the
-- same endpoint that sets them, so the two cannot drift.
CREATE TABLE IF NOT EXISTS tripassignments (
  recordid       VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid      VARCHAR(36)  NOT NULL,
  legid          VARCHAR(36)  NOT NULL,
  driverid       VARCHAR(36)  NULL,
  vehicleid      VARCHAR(36)  NULL,
  assignedon     DATETIME     NOT NULL,
  assignedby     VARCHAR(36)  NULL,
  endedon        DATETIME     NULL,       -- NULL means this is the one in force
  endedby        VARCHAR(36)  NULL,
  endreason      VARCHAR(32)  NULL,
  -- Phase 2 fills these from the driver's app. The columns exist now so that the day it arrives
  -- is not also the day the table changes shape under live data.
  acknowledgedon DATETIME     NULL,
  declinedon     DATETIME     NULL,
  -- A warning was accepted by somebody who had to say why. A hard block has no row here, because
  -- a hard block is never assigned in the first place.
  override       TINYINT(1)   NOT NULL DEFAULT 0,
  overridereason VARCHAR(400) NULL,
  KEY ix_tripassignments_leg (accountid, legid, endedon),
  KEY ix_tripassignments_driver (accountid, driverid, assignedon)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------------------------
-- What was returned to a broker
-- -----------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS triprejections (
  recordid        VARCHAR(36) NOT NULL PRIMARY KEY,
  accountid       VARCHAR(36) NOT NULL,
  tripid          VARCHAR(36) NOT NULL,
  reason          VARCHAR(32) NOT NULL,
  note            VARCHAR(600) NULL,
  requestedon     DATETIME    NOT NULL,
  requestedby     VARCHAR(36) NULL,
  -- When it actually left for the broker, and by what road. A rejection recorded here and never
  -- sent is the worst of both: the office believes it is gone and the broker is still waiting.
  senton          DATETIME    NULL,
  sentby          VARCHAR(16) NULL,       -- api | portal | phone
  acknowledgedon  DATETIME    NULL,
  acknowledgedref VARCHAR(64) NULL,
  KEY ix_triprejections_trip (accountid, tripid, requestedon)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------------------------
-- When somebody or something cannot be used
-- -----------------------------------------------------------------------------------------------
-- Deliberately the negative. A table saying when a driver IS available has to be filled in before
-- the product works at all; a table of exceptions is empty on the first day and still correct.
CREATE TABLE IF NOT EXISTS driverunavailable (
  recordid  VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid VARCHAR(36)  NOT NULL,
  driverid  VARCHAR(36)  NOT NULL,
  fromat    DATETIME     NOT NULL,
  untilat   DATETIME     NOT NULL,
  reason    VARCHAR(32)  NOT NULL,
  note      VARCHAR(200) NULL,
  added     DATETIME     NOT NULL,
  addedby   VARCHAR(36)  NULL,
  KEY ix_driverunavailable (accountid, driverid, fromat, untilat)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vehicleunavailable (
  recordid  VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid VARCHAR(36)  NOT NULL,
  vehicleid VARCHAR(36)  NOT NULL,
  fromat    DATETIME     NOT NULL,
  untilat   DATETIME     NOT NULL,
  reason    VARCHAR(32)  NOT NULL,
  note      VARCHAR(200) NULL,
  added     DATETIME     NOT NULL,
  addedby   VARCHAR(36)  NULL,
  KEY ix_vehicleunavailable (accountid, vehicleid, fromat, untilat)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- MariaDB 11.8 creates a table in ITS default collation - utf8mb4_uca1400_ai_ci - not in the
-- database's, and this schema is utf8mb4_unicode_ci throughout. A new table left on the server's
-- default cannot be joined to an old one: comparing its varchar key to theirs raises "illegal mix
-- of collations" and the join simply fails. The CREATEs above say which collation they want, and
-- these four lines put right any table created before they did.
ALTER TABLE tripassignments    CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE triprejections     CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE driverunavailable  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE vehicleunavailable CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------------------------
-- What is already true of the trips on file
-- -----------------------------------------------------------------------------------------------
-- A trip that came from a broker is one the company is already carrying - it was imported as work,
-- not as an offer. Calling every historical trip "offered" would put the whole file into the
-- incoming queue on the morning this ships.
UPDATE trips SET brokerstate = 'accepted' WHERE brokerid IS NOT NULL AND brokerstate = 'none';

UPDATE trips t SET dispatchstate = 'assigned'
 WHERE dispatchstate = 'unassigned'
   AND EXISTS (SELECT 1 FROM triplegs l WHERE l.tripid = t.recordid AND l.driverid IS NOT NULL);

-- A leg with a drop-off time recorded is a leg that was driven.
UPDATE triplegs SET executionstate = 'completed'
 WHERE dropoffat IS NOT NULL AND executionstate = 'scheduled';

-- The assignment in force on every leg that has one, as the history's first entry. `added` is the
-- only honest date available for when it was made - it is when the leg was written.
INSERT INTO tripassignments (recordid, accountid, legid, driverid, vehicleid, assignedon,
                             assignedby, endreason)
SELECT UUID(), l.accountid, l.recordid, l.driverid, l.vehicleid, l.added, NULL, NULL
  FROM triplegs l
  JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
 WHERE (l.driverid IS NOT NULL OR l.vehicleid IS NOT NULL)
   AND NOT EXISTS (SELECT 1 FROM tripassignments a WHERE a.legid = l.recordid);
