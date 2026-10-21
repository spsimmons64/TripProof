-- The driver's own app: signing in, and the three things that happen out on the road.
--
-- Until now a driver could not sign in to anything. They reached TripProof only through one-time
-- links - an upload, a signature, an application - because every screen was the office's. The app
-- changes that, so a driver needs a credential of their own, and the record of what happened on a
-- trip needs somewhere to go that is not a dispatcher typing down a telephone call.
--
-- Three things are added, in the order they matter:
--
--   A LOGIN ON THE DRIVER. The same machinery the office has - bcrypt, an invitation to set it,
--   a reset by email - against the driver record rather than a user record. A driver is not a
--   user: they have no account-wide permissions and must never be able to act as one, which is
--   why this is a column on `drivers` and not a row in `users`.
--
--   WAITING. The fee schedule already prices waiting time, by the minute and by the quarter hour,
--   and nothing anywhere recorded a minute of it. A wait is a span with a beginning and an end,
--   because that is the only shape that can be billed and the only shape that can be disputed.
--
--   AN ISSUE RAISED FROM THE ROAD. A driver who cannot complete a trip has, today, a telephone.
--   An issue is a record with a time on it, an owner, and a resolution, so that it survives a
--   shift change instead of living in somebody's memory.

-- -----------------------------------------------------------------------------------------------
-- A login on the driver
-- -----------------------------------------------------------------------------------------------
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS passwordhash  VARCHAR(100) NULL;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS passwordseton DATETIME NULL;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS lastloginon   DATETIME NULL;
-- Being able to drive and being able to sign in are different questions. A driver stood down for
-- a week is still qualified; a driver whose app access is withdrawn may still be on the roster.
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS appaccess     TINYINT(1) NOT NULL DEFAULT 1;

-- Invitations and resets go through the table that already does that job rather than a second one
-- beside it. `userid` becomes nullable and `driverid` joins it; exactly one is set.
ALTER TABLE passwordtokens ADD COLUMN IF NOT EXISTS driverid VARCHAR(36) NULL AFTER userid;
ALTER TABLE passwordtokens MODIFY COLUMN userid VARCHAR(36) NULL;
ALTER TABLE passwordtokens DROP CONSTRAINT IF EXISTS ck_passwordtokens_subject;
ALTER TABLE passwordtokens ADD CONSTRAINT ck_passwordtokens_subject CHECK (
  (userid IS NOT NULL AND driverid IS NULL) OR (userid IS NULL AND driverid IS NOT NULL));

-- -----------------------------------------------------------------------------------------------
-- Waiting
-- -----------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tripwaits (
  recordid   VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid  VARCHAR(36)  NOT NULL,
  legid      VARCHAR(36)  NOT NULL,
  driverid   VARCHAR(36)  NULL,
  startedon  DATETIME     NOT NULL,
  endedon    DATETIME     NULL,          -- NULL means the clock is still running
  reason     VARCHAR(32)  NULL,          -- appointment | passenger | facility | other
  note       VARCHAR(300) NULL,
  -- Where the vehicle was when it started waiting. A wait billed at a place nobody can name is a
  -- wait that gets argued about.
  latitude   DECIMAL(9,6) NULL,
  longitude  DECIMAL(9,6) NULL,
  added      DATETIME     NOT NULL,
  KEY ix_tripwaits_leg (accountid, legid, startedon)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------------------------
-- An issue raised from the road
-- -----------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tripissues (
  recordid       VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid      VARCHAR(36)  NOT NULL,
  tripid         VARCHAR(36)  NOT NULL,
  legid          VARCHAR(36)  NULL,
  driverid       VARCHAR(36)  NULL,
  kind           VARCHAR(32)  NOT NULL,  -- noshow | refused | address | vehicle | medical |
                                         -- traffic | equipment | other
  note           VARCHAR(600) NULL,
  raisedon       DATETIME     NOT NULL,
  latitude       DECIMAL(9,6) NULL,
  longitude      DECIMAL(9,6) NULL,
  -- Seen by the office, and then dealt with. Two moments, not one: a dispatcher reading it is not
  -- the same as the problem going away, and an issue list that cannot tell them apart is a list
  -- nobody trusts.
  acknowledgedon DATETIME     NULL,
  acknowledgedby VARCHAR(36)  NULL,
  resolvedon     DATETIME     NULL,
  resolvedby     VARCHAR(36)  NULL,
  resolution     VARCHAR(600) NULL,
  KEY ix_tripissues_open (accountid, resolvedon, raisedon),
  KEY ix_tripissues_trip (accountid, tripid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
