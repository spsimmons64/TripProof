-- Where things are.
--
-- The dashboard shows a map: the company's base, and each driver's last known position. Two
-- things were missing for that - the base is a street address and nothing had ever worked out
-- where that is, and a driver's position had nowhere to be recorded at all.
--
-- A driver's HOME address is not their last known position, so it is not used for this. An
-- empty map that says nobody has reported is honest; a map showing four drivers parked at
-- their houses is not.

ALTER TABLE accounts
  ADD COLUMN IF NOT EXISTS latitude  DECIMAL(9,6) NULL,
  ADD COLUMN IF NOT EXISTS longitude DECIMAL(9,6) NULL,
  -- When the address was last turned into a position, so a changed address can be noticed
  -- and looked up again rather than leaving the pin on the old place.
  ADD COLUMN IF NOT EXISTS locatedon DATETIME NULL,
  ADD COLUMN IF NOT EXISTS locatedfor VARCHAR(255) NULL;

-- One row per report. Kept rather than overwritten: "where was this driver at 14:20" is a
-- question an accident investigation asks, and a single current-position column cannot answer
-- it. The map reads the latest per driver.
CREATE TABLE IF NOT EXISTS driverlocations (
  recordid    VARCHAR(36)  NOT NULL,
  accountid   VARCHAR(36)  NOT NULL,
  driverid    VARCHAR(36)  NOT NULL,
  latitude    DECIMAL(9,6) NOT NULL,
  longitude   DECIMAL(9,6) NOT NULL,
  -- Metres, as a phone reports it. Null where the source did not say.
  accuracy    INT              NULL,
  speed       DECIMAL(6,2)     NULL,
  heading     INT              NULL,
  -- The moment the position was TAKEN, which is not the moment it arrived here: a phone out
  -- of signal reports a backlog, and plotting those by arrival time would draw a route the
  -- vehicle never drove.
  recordedon  DATETIME     NOT NULL,
  added       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
  source      VARCHAR(32)      NULL,
  PRIMARY KEY (recordid),
  KEY ix_driverlocations_latest (accountid, driverid, recordedon),
  CONSTRAINT fk_driverlocations_driver
    FOREIGN KEY (driverid) REFERENCES drivers (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
