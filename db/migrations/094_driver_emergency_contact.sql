-- ################################################################################################
-- # 094 - who to call, on the driver's record rather than inside their application.
-- #
-- # The applicant gives an emergency contact on the way through, and it has been sitting in the
-- # application's JSON ever since - a record of what they said on the day, which is not the same
-- # thing as a number the office can ring this afternoon. A contact changes; the application does
-- # not, and should not.
-- #
-- # So it moves onto the driver, where the office can keep it current, and what is already on file
-- # comes with it.
-- ################################################################################################
ALTER TABLE drivers
    ADD COLUMN emergencyname  VARCHAR(128) NULL AFTER phone,
    ADD COLUMN emergencyphone VARCHAR(32)  NULL AFTER emergencyname;

UPDATE drivers d
  JOIN driverapplications a ON a.driverid = d.recordid
   SET d.emergencyname  = COALESCE(d.emergencyname,
         JSON_UNQUOTE(JSON_EXTRACT(a.data, '$.steps."1".emergencyname'))),
       d.emergencyphone = COALESCE(d.emergencyphone,
         JSON_UNQUOTE(JSON_EXTRACT(a.data, '$.steps."1".emergencyphone')))
 WHERE JSON_EXTRACT(a.data, '$.steps."1".emergencyname') IS NOT NULL;
