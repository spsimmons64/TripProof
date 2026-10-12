-- ################################################################################################
-- # 148 - the questionnaire can be asked for after the application is in.
-- #
-- # 40.25(j) is a question only the applicant can answer, and an application that was submitted
-- # before this existed does not contain it. Rather than invent a second request mechanism, it is
-- # asked for the way every other thing asked of a driver is asked for - a row in `uploadrequests`,
-- # a token, an email, the same date of birth and Social Security check at the other end.
-- #
-- # That machinery keys off a credential type, so the questionnaire has one. Nothing is filed
-- # against it: what comes back is an answer, and the answer goes onto the driver's application
-- # where the rule already reads it. The type exists so the request has something to name.
-- ################################################################################################

INSERT INTO credentialtypes (recordid, code, name, subject, active)
SELECT UUID(), 'PREEMP_DA_QUESTIONNAIRE',
       'Pre-employment drug and alcohol questionnaire', 'driver', 1
 WHERE NOT EXISTS (SELECT 1 FROM credentialtypes WHERE code = 'PREEMP_DA_QUESTIONNAIRE');
