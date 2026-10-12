-- ################################################################################################
-- # 081 - a driving record nobody has reviewed disqualifies the driver.
-- #
-- # 49 CFR 391.25 asks the carrier to obtain the driver's motor vehicle record at least yearly and
-- # to review it, noting whether the driver still meets the qualification standards. So a record
-- # that arrives after the last review has not been reviewed - and a driver whose record is sitting
-- # unread is not qualified to drive until someone has read it and said so.
-- #
-- # That is a check of its own: not a document that expires, but two dates in the wrong order.
-- ################################################################################################
ALTER TABLE requirements DROP CONSTRAINT IF EXISTS ck_requirements_kind;
ALTER TABLE requirements
    ADD CONSTRAINT ck_requirements_kind CHECK (kind IN ('credential', 'vehiclemileage', 'vehicleage',
        'driverage', 'licenseyears', 'tripevidence', 'obligation', 'licenceclass', 'annualreview'));
