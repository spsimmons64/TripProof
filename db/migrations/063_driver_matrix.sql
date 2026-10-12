-- ################################################################################################
-- # 063 - the driver matrix, as given: what every driver needs, what only a Part 391 driver needs,
-- # and what waits on a trigger.
-- #
-- # Three changes were outstanding against it:
-- #   - federal exclusion screening is conditional on the trips being Medicaid funded, not flat
-- #   - the CDL itself was missing from the catalog
-- #   - so was the passenger endorsement
-- ################################################################################################

-- The assurance is owed because the money is Medicaid's. A company carrying nothing Medicaid funded
-- is not under it, so it says so rather than being asked of everyone.
UPDATE compliancedocs
   SET obligation = 'conditional', classification = 'conditional',
       appliesif  = 'The company carries Medicaid-funded trips',
       whendue    = 'Before the driver carries a Medicaid passenger'
 WHERE subject = 'driver' AND code = 'EXCLUSION_CHECK_DRIVER';

-- The licence itself, when the vehicle is one a CDL is needed for, and the endorsement that goes
-- with carrying passengers. Both carry their own expiry date, so neither gets a period.
INSERT IGNORE INTO compliancedocs
    (recordid, jurisdiction, sourcecode, subject, code, name, obligation, classification, requiredfor,
     category, expires, validdays, driversign, renewal, whendue, retention, appliesif, description,
     legalcitation, authority, sortorder, active)
VALUES
 (UUID(), 'US', 'FED_FMCSA', 'driver', 'CDL_LICENSE', 'Commercial driver''s license of the right class',
  'conditional', 'conditional', 'cdl', 'licensing', 1, NULL, 0,
  'Expiry printed on the license', 'Before driving the vehicle', 'While the driver is employed',
  'The vehicle is one that requires a commercial driver''s license',
  'A CDL of the class the vehicle calls for, held by the driver operating it. Which class, and '
  'whether a CDL is needed at all, follows the vehicle rather than the work.',
  '49 CFR 383.23; 49 CFR 383.5', 'FMCSA', 122, 1),
 (UUID(), 'US', 'FED_FMCSA', 'driver', 'CDL_PASSENGER_ENDORSEMENT', 'CDL passenger (P) endorsement',
  'conditional', 'conditional', 'cdl', 'licensing', 1, NULL, 0,
  'Expiry printed on the license', 'Before driving the vehicle', 'While the driver is employed',
  'The vehicle is designed to carry 16 or more people including the driver',
  'The passenger endorsement on the driver''s CDL, with the knowledge and skills tests behind it.',
  '49 CFR 383.93(b)(1)', 'FMCSA', 123, 1);

-- Every account's own list picks the two new ones up at the level the catalog sets.
INSERT IGNORE INTO accountqualifications
    (recordid, accountid, code, catalog, obligation, requiredfor, expires, validdays, sortorder)
SELECT UUID(), a.recordid, c.code, 1, c.obligation, c.requiredfor, c.expires, c.validdays, c.sortorder
FROM accounts a
CROSS JOIN compliancedocs c
WHERE a.deleted IS NULL AND a.platform = 0 AND c.subject = 'driver'
  AND c.code IN ('CDL_LICENSE', 'CDL_PASSENGER_ENDORSEMENT');

UPDATE accountqualifications q
  JOIN compliancedocs c ON c.code = q.code AND c.subject = 'driver'
   SET q.obligation = c.obligation
 WHERE q.catalog = 1 AND q.updated IS NULL AND q.code = 'EXCLUSION_CHECK_DRIVER';
