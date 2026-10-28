-- ################################################################################################
-- # 361 - a driver may change vehicles during the day.
-- #
-- # One shift per driver per day could not say "in MT-SEDAN2 until noon, then MT-SEDAN1". A driver
-- # may now have several shifts on one day, so long as they do not overlap (app/shifts.clash).
-- ################################################################################################

ALTER TABLE dayshifts DROP INDEX IF EXISTS ux_dayshifts_driver;
CREATE INDEX IF NOT EXISTS ix_dayshifts_driver ON dayshifts (accountid, workday, driverid);
