-- ################################################################################################
-- # 383 - capacity is drivers, not a schedule of vehicles.
-- #
-- # Every vehicle in service is there every day unless it is out or not compliant; what changes
-- # from day to day is who works. Each driver's regular days (Mon to Fri, or Mon/Wed/Fri) - none
-- # recorded is every day the company is open - and time off is Driver Out. Drivers are put into
-- # vehicles on the day itself. The weekly vehicle schedule, and runs with no driver, go.
-- ################################################################################################

ALTER TABLE drivers ADD COLUMN IF NOT EXISTS workdays VARCHAR(7) NULL;   -- weekday digits, 0 Monday

DROP TABLE IF EXISTS usualruns;
DELETE FROM dayshifts WHERE driverid IS NULL;
