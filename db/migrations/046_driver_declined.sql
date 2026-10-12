-- ################################################################################################
-- # 046 - a driver who will not be hired.
-- #
-- # drivers.status    application  a form in progress, or sent back for corrections
-- #                   new          the application is complete and waiting for the office
-- #                   pending      under review - screenings and verifications under way
-- #                   active       cleared to drive
-- #                   inactive     no longer driving
-- #                   declined     not approved for employment; kept for the record, cannot go active
-- ################################################################################################
ALTER TABLE drivers DROP CONSTRAINT IF EXISTS ck_drivers_status;

ALTER TABLE drivers
    ADD CONSTRAINT ck_drivers_status
        CHECK (status IN ('application', 'new', 'pending', 'active', 'inactive', 'declined'));
