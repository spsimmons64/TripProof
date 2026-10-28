-- ################################################################################################
-- # 365 - a passenger's and a place's address in its parts, where it is on the map, and the time a
-- # passenger has to BE somewhere.
-- #
-- # The street stays in `address`; city, state and ZIP beside it, so a pickup or drop-off is an
-- # address the geocoder can find. The position is looked up once, when the entry is added, and is
-- # what the route to it is worked out from. A leg's appointment time is the hour the passenger is
-- # due at the drop-off; the pickup is worked back from it (app/routing.py).
-- ################################################################################################

ALTER TABLE places     ADD COLUMN IF NOT EXISTS city  VARCHAR(80) NULL AFTER address;
ALTER TABLE places     ADD COLUMN IF NOT EXISTS state CHAR(2)     NULL AFTER city;
ALTER TABLE places     ADD COLUMN IF NOT EXISTS zip   VARCHAR(10) NULL AFTER state;
ALTER TABLE places     ADD COLUMN IF NOT EXISTS lat   DECIMAL(10,7) NULL AFTER zip;
ALTER TABLE places     ADD COLUMN IF NOT EXISTS lng   DECIMAL(10,7) NULL AFTER lat;
ALTER TABLE passengers ADD COLUMN IF NOT EXISTS city  VARCHAR(80) NULL AFTER address;
ALTER TABLE passengers ADD COLUMN IF NOT EXISTS state CHAR(2)     NULL AFTER city;
ALTER TABLE passengers ADD COLUMN IF NOT EXISTS zip   VARCHAR(10) NULL AFTER state;
ALTER TABLE passengers ADD COLUMN IF NOT EXISTS lat   DECIMAL(10,7) NULL AFTER zip;
ALTER TABLE passengers ADD COLUMN IF NOT EXISTS lng   DECIMAL(10,7) NULL AFTER lat;

ALTER TABLE triplegs   ADD COLUMN IF NOT EXISTS appointmentat DATETIME NULL AFTER dropoffat;
