-- ################################################################################################
-- # 080 - the annual review of driving record.
-- #
-- # 49 CFR 391.25: at least once every twelve months the carrier must obtain the driver's motor
-- # vehicle record and review it, and note the review - whether the driver meets the qualification
-- # standards, and who considered it. 391.51(b)(4) keeps that note in the driver qualification file.
-- #
-- # It is a credential like any other: it is issued on a date, it goes stale after twelve months,
-- # and a trip after that is driven by someone whose record nobody has looked at.
-- ################################################################################################
INSERT IGNORE INTO credentialtypes (recordid, code, name, subject, maxagedays, defaultvaliddays,
                                    category, description, active)
VALUES (UUID(), 'ANNUAL_REVIEW', 'Annual review of driving record', 'driver', 365, NULL, 'screening',
        'The carrier''s note of its yearly review of the driver''s motor vehicle record, and whether '
        'the driver meets the qualification standards', 1);

UPDATE compliancedocs
   SET credentialtypeid = (SELECT recordid FROM credentialtypes WHERE code = 'ANNUAL_REVIEW')
 WHERE subject = 'driver' AND code = 'MVR_ANNUAL';
