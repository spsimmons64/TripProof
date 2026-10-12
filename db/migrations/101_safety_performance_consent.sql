-- ################################################################################################
-- # 101 - the consent that makes the safety performance history possible.
-- #
-- # 49 CFR 391.23(g): before a carrier can ask a driver's previous DOT employers what it is
-- # required to ask - accidents, and drug and alcohol violations - the driver has to have given
-- # written consent. 40.25(g) says the same about the testing records specifically.
-- #
-- # The catalog held the history but not the consent, so the file could show the investigation as
-- # complete with nothing on record saying the driver had ever agreed to it. The driver signs it in
-- # the application already; what was missing was the line item the office reads.
-- ################################################################################################
INSERT IGNORE INTO compliancedocs
    (recordid, jurisdiction, sourcecode, subject, code, name, obligation, classification,
     requiredfor, category, stage, expires, driversign, whendue, retention, appliesif, description,
     legalcitation, authority, sourceurl, sortorder, active, added)
VALUES (UUID(), 'US', 'FED_FMCSA', 'driver', 'SAFETY_PERFORMANCE_CONSENT',
        'Consent to release safety performance history', 'conditional', 'conditional', 'cdl',
        'screening', 'prehire', 0, 1,
        'Signed before the previous employers are asked',
        'Three years from the date of the inquiry',
        'Drivers of commercial motor vehicles',
        'The driver''s written consent for this company to obtain their accident record and their '
        'drug and alcohol testing history from the DOT-regulated employers they worked for in the '
        'previous three years.',
        '49 CFR 391.23(g); 49 CFR 40.25(g)', 'FMCSA',
        'https://www.ecfr.gov/current/title-49/section-391.23', 179, 1, UTC_TIMESTAMP());

-- Every account carries its own copy of the list, so the new item reaches the ones that exist.
INSERT IGNORE INTO accountqualifications
    (recordid, accountid, subject, code, catalog, stage, applies, obligation, requiredfor, expires,
     validdays, sortorder)
SELECT UUID(), a.recordid, c.subject, c.code, 1, c.stage, c.requiredfor, c.obligation,
       c.requiredfor, c.expires, c.validdays, c.sortorder
  FROM accounts a
  CROSS JOIN compliancedocs c
 WHERE c.code = 'SAFETY_PERFORMANCE_CONSENT' AND a.deleted IS NULL;
