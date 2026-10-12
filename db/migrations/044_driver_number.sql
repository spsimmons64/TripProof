-- ################################################################################################
-- # 044 - every driver gets a number of their own.
-- #
-- # drivers.externalid is the driver's key in the customer's dispatch system: the trip importer
-- # matches on it, and it is empty for anyone who arrived through the online application. It was
-- # never an identifier we could count on, so the Driver ID is ours now.
-- #
-- # drivernumber is assigned when the record is created, whatever created it, and runs from 1001
-- # within each account - so one company's numbering says nothing about another's. Existing
-- # drivers are numbered in the order they were added.
-- ################################################################################################
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS drivernumber INT NULL AFTER externalid;

UPDATE drivers d
  JOIN (SELECT recordid,
               1000 + ROW_NUMBER() OVER (PARTITION BY accountid ORDER BY added, recordid) AS n
          FROM drivers) x ON x.recordid = d.recordid
   SET d.drivernumber = x.n
 WHERE d.drivernumber IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_drivers_number ON drivers (accountid, drivernumber);
