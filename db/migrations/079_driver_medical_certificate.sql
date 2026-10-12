-- ################################################################################################
-- # 079 - the driver's medical certificate, named for whose it is.
-- #
-- # "Medical examiner's certificate" names the instrument the examiner issues. What the file holds,
-- # and what the driver carries, is their own certificate - the same wording the exhibit already
-- # uses for the copy attached to the application.
-- ################################################################################################
UPDATE compliancedocs SET name = 'Driver medical certificate'
 WHERE subject = 'driver' AND code = 'MEDICAL_CERT';

UPDATE credentialtypes SET name = 'Driver medical certificate'
 WHERE code = 'DOT_MEDICAL_CARD';
