-- ################################################################################################
-- # 043 - a finished application makes the driver "new", not "pending".
-- #
-- # drivers.status    application  a form in progress, not yet submitted
-- #                   new          the application is complete and waiting for the office
-- #                   pending      the office is working through it - checks under way
-- #                   active       cleared to drive
-- #                   inactive     no longer driving
-- #
-- # Applications already submitted under the old wording move across, so the Drivers grid shows
-- # them where the office expects to find them.
-- ################################################################################################
ALTER TABLE drivers DROP CONSTRAINT IF EXISTS ck_drivers_status;

ALTER TABLE drivers
    ADD CONSTRAINT ck_drivers_status
        CHECK (status IN ('application', 'new', 'pending', 'active', 'inactive'));

UPDATE drivers d
   JOIN driverapplications a ON a.driverid = d.recordid
    SET d.status = 'new'
  WHERE d.status = 'pending' AND a.status = 'submitted';
