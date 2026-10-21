-- When each thing happened on a leg, not just where it has got to.
--
-- `triplegs.executionstate` says where a leg IS. It cannot say when it got there, and it forgets
-- every step the moment the next one is taken: a completed trip looks identical whether the driver
-- arrived at 9:02 and left at 9:40, or arrived at 10:30 having never reported being on the way.
--
-- For a broker asking why a passenger reached dialysis late, or an auditor asking what this
-- company actually did on 15 October, "completed" is not an answer. Each transition is now its own
-- row, with the moment it happened, who reported it, and where they were.
--
-- Appended, never updated. A correction is another row, not a rewrite of this one.

CREATE TABLE IF NOT EXISTS tripevents (
  recordid   VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid  VARCHAR(36)  NOT NULL,
  legid      VARCHAR(36)  NOT NULL,
  state      VARCHAR(16)  NOT NULL,   -- enroute | arrived | onboard | completed
  happenedon DATETIME     NOT NULL,   -- as the device reported it, never later than it arrived
  recordedon DATETIME     NOT NULL,   -- when it reached us; the two differ out of signal
  driverid   VARCHAR(36)  NULL,
  byuserid   VARCHAR(36)  NULL,       -- where the office moved it instead of the driver
  latitude   DECIMAL(9,6) NULL,
  longitude  DECIMAL(9,6) NULL,
  KEY ix_tripevents_leg (accountid, legid, happenedon)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- What is already known about the legs on file. A completed leg has a drop-off time, and that is
-- a real event that happened; nothing else can be reconstructed, and inventing an arrival time
-- for a trip driven last week would be worse than leaving the gap visible.
INSERT INTO tripevents (recordid, accountid, legid, state, happenedon, recordedon, driverid)
SELECT UUID(), l.accountid, l.recordid, 'completed', l.dropoffat, l.dropoffat, l.driverid
  FROM triplegs l JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
 WHERE l.dropoffat IS NOT NULL AND l.executionstate = 'completed'
   AND NOT EXISTS (SELECT 1 FROM tripevents e
                    WHERE e.legid = l.recordid AND e.state = 'completed');
