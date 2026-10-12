-- ################################################################################################
-- # 070 - the licence a driver holds, kept where a trip can be judged against it.
-- #
-- # The vehicle says which licence its driver needs (seats over 15, or 26,001 lb and up). The driver
-- # says which one they hold - on their application, and in the barcode on the back of the card. The
-- # two have never met: the class and the endorsements sat inside the application's JSON, where no
-- # trip check could read them.
-- #
-- # They live on the driver record now, so a leg can ask the only question that matters: was the
-- # person driving that vehicle licensed for it on that day.
-- ################################################################################################
ALTER TABLE drivers
    ADD COLUMN licenseclass  VARCHAR(2)  NULL AFTER licensestate,
    ADD COLUMN endorsements  VARCHAR(16) NULL AFTER licenseclass;

-- A new kind of check: not a document that expires, but whether the licence fits the vehicle driven.
ALTER TABLE requirements DROP CONSTRAINT IF EXISTS ck_requirements_kind;
ALTER TABLE requirements
    ADD CONSTRAINT ck_requirements_kind CHECK (kind IN ('credential', 'vehiclemileage', 'vehicleage',
        'driverage', 'licenseyears', 'tripevidence', 'obligation', 'licenceclass'));

-- What the applications already on file said, so nothing has to be re-entered.
UPDATE drivers d
  JOIN driverapplications a ON a.driverid = d.recordid
   SET d.licenseclass = JSON_UNQUOTE(JSON_EXTRACT(a.data, '$.steps."2".licenses[0].classification')),
       d.endorsements = JSON_UNQUOTE(JSON_EXTRACT(a.data, '$.steps."2".licenses[0].endorsements'))
 WHERE d.licenseclass IS NULL
   AND JSON_EXTRACT(a.data, '$.steps."2".licenses[0].classification') IS NOT NULL;
