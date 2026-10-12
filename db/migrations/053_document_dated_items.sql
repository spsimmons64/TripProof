-- ################################################################################################
-- # 053 - the things that carry their own expiry date.
-- #
-- # A driver's licence runs out on the date printed on it. A medical examiner's certificate runs
-- # out on the date the examiner wrote, which may be two years or may be three months if they
-- # shortened it. Neither is "good for N days from the day it was filed", so neither gets a period:
-- # filing one asks for the date on the document and uses that.
-- ################################################################################################
UPDATE compliancedocs SET validdays = NULL
 WHERE subject = 'driver' AND code IN ('DRIVER_LICENSE_COPY', 'MEDICAL_CERT');

UPDATE accountqualifications SET validdays = NULL
 WHERE catalog = 1 AND code IN ('DRIVER_LICENSE_COPY', 'MEDICAL_CERT');
