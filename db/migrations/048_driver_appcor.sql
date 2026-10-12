-- ################################################################################################
-- # 048 - a status of its own for an application sent back to the driver.
-- #
-- # Until now a corrected application went back to 'application', which reads as "never finished"
-- # and is indistinguishable from an applicant who is still typing. The office needs to see that
-- # this one was read, returned, and is waiting on the driver again.
-- #
-- # drivers.status    application  a form in progress, not yet submitted
-- #                   appcor       submitted, read, and sent back to the driver to correct
-- #                   new          the application is complete and waiting for the office
-- #                   pending      under review - screenings and verifications under way
-- #                   active       cleared to drive
-- #                   inactive     no longer driving
-- #                   declined     not approved for employment; kept for the record
-- ################################################################################################
ALTER TABLE drivers DROP CONSTRAINT IF EXISTS ck_drivers_status;

ALTER TABLE drivers
    ADD CONSTRAINT ck_drivers_status
        CHECK (status IN ('application', 'appcor', 'new', 'pending', 'active', 'inactive', 'declined'));

-- Anyone already sitting in 'application' with a reviewed, returned form belongs in the new status.
UPDATE drivers d
  JOIN driverapplications a ON a.driverid = d.recordid
   SET d.status = 'appcor'
 WHERE d.status = 'application' AND a.status = 'started' AND a.reviewedon IS NOT NULL;
