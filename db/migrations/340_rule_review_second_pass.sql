-- ################################################################################################
-- # 340 - the second review of the rule packet (2026-10-22).
-- #
-- # Each change is read against its source, not taken from the review:
-- #   F.S. 316.302(2)(a) and (4) (flsenate.gov, 2026); DCH NEMT Part II (October 2026) 608.6,
-- #   608.7, 608.8, 907.15, 910.1, 910.2, 914.2.4, 915.1.1, 1006.5.3.
-- # Where no source could be read - the Georgia DHS manual - the rule says so rather than guess.
-- # Every rule stays a draft, approved by whoever reads it.
-- ################################################################################################

ALTER TABLE compliancerules
  ADD COLUMN IF NOT EXISTS recurrencemonths SMALLINT NULL AFTER recurrencedays;

-- --- Driver age ---------------------------------------------------------------------------------

-- 391.11(b)(1)'s twenty-one reaches a driver only where the federal rules do it themselves. A
-- Florida intrastate driver is reached by Florida's adoption of Part 391, and F.S. 316.302(2)(a)
-- excuses them the federal age.
UPDATE compliancerules SET applieswhen = '{"fact":"reach.part391interstate","is":true}'
 WHERE code = 'DRIVER_AGE' AND accountid IS NULL AND effectiveto IS NULL;

-- F.S. 316.302(4): nobody under eighteen operates a CMV in Florida. The same qualification as the
-- federal and Georgia ages, so one age shows on the driver however many reach them.
INSERT INTO compliancerules (recordid, accountid, code, qualificationcode, name, description,
  templatedocumentid, subject, authoritytype, authoritycategory, authority, jurisdiction, citation,
  sourceurl, applieswhen, program, evidencekind, evidencesource, origin, extendable, extendnote,
  offered, alternatesource, alternatewhen, reviewrequired, determination, blocking, gate,
  enforcement, legalreview, legalreviewedby, legalreviewedon, grouping, duestage, duedays, duetext,
  recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule,
  effectivefrom, effectiveto, supersedes, note, sortorder, added, addedby)
SELECT UUID(), NULL, 'FL_INTRASTATE_AGE18', r.qualificationcode,
  'Driver at least 18 (Florida intrastate)',
  'A driver of a commercial motor vehicle solely in Florida intrastate commerce, not carrying hazardous materials, is excused the federal minimum age of 21 (F.S. 316.302(2)(a)) and must be at least 18 (F.S. 316.302(4)). Read from the date of birth on the driver record; there is nothing to file.',
  NULL, 'driver', 'regulation', 'STATE_GENERAL', 'Florida', 'FL', 'F.S. 316.302(2)(a) and (4)',
  'https://www.flsenate.gov/Laws/Statutes/2026/316.302',
  '{"all":[{"fact":"reach.part391","is":true},{"fact":"reach.part391interstate","is":false}]}',
  NULL, 'fact', 'driverfact:driver.age18', r.origin,
  0, NULL, 0, NULL, NULL, 0, 0, 1, r.gate, r.enforcement, 'draft', NULL, NULL, r.grouping,
  r.duestage, NULL, NULL, 'once', 0, NULL, 0,
  r.warndays, r.sensitivity, NULL, CURDATE(), NULL, NULL, NULL, r.sortorder, UTC_TIMESTAMP(), NULL
FROM compliancerules r
WHERE r.code = 'DRIVER_AGE' AND r.accountid IS NULL AND r.effectiveto IS NULL
  AND NOT EXISTS (SELECT 1 FROM compliancerules x WHERE x.code = 'FL_INTRASTATE_AGE18');

-- --- Georgia vehicle inspection: six calendar months --------------------------------------------

-- DCH 910.2: "no later than six (6) months after the most recent inspection". 183 days is not that
-- date, and the engine now counts calendar months.
UPDATE compliancerules SET recurrence = 'months', recurrencedays = NULL, recurrencemonths = 6
 WHERE code = 'GA_NET_VEHICLE_INSPECTION' AND accountid IS NULL AND effectiveto IS NULL;

-- --- Duties DCH places on the broker ------------------------------------------------------------

-- DCH 608.6 is about the BROKER's own owners and managing employees, and the monthly check is the
-- broker's. Nothing in it is the provider's to file. The provider's own exclusion duty - each
-- provider and driver not on the OIG list (915.1.1) - is GA_NET_OIG, which stays.
UPDATE compliancerules SET effectiveto = CURDATE(),
       note = 'Retired 2026-10-22: DCH 608.6 is the broker''s check of its own owners, not a provider duty.'
 WHERE code = 'GA_NET_OWNER_EXCLUSION' AND accountid IS NULL AND effectiveto IS NULL;

-- DCH 608.7: the broker checks the Death Master File. A company whose broker asks it to carry the
-- check still files it here, but it does not stop a trip - DCH did not put it on the provider.
UPDATE compliancerules SET blocking = 0
 WHERE code = 'GA_NET_DMF' AND accountid IS NULL AND effectiveto IS NULL;

-- --- Georgia driving record ---------------------------------------------------------------------

-- DCH 1006.5.3 asks for a three-year record and names no renewal; 907.15 and 914.2.4 bar a
-- suspension or revocation in the last five years. The record is read for that (reviewrequired
-- was already set), and is not renewed on a cycle the manual does not state.
UPDATE compliancerules SET recurrence = 'once', recurrencedays = NULL,
       description = 'Georgia Medicaid NEMT: the provider keeps a three-year driving record for each driver (DCH 1006.5.3), and no driver may have had a suspended or revoked license, commercial or other, in the last five years (907.15, 914.2.4). The record on file answers it once somebody has read it for that. The manual names the Georgia State Patrol as the source; Georgia driving records are issued by the Department of Driver Services - confirm with the broker which it accepts.',
       note = 'No renewal interval stated in DCH Part II (October 2026); confirm with the broker.'
 WHERE code = 'GA_NET_MVR' AND accountid IS NULL AND effectiveto IS NULL;

-- --- Georgia background check -------------------------------------------------------------------

-- 914.2.2 and 914.2.3 are judged from what the report says, not the vendor's summary: a report on
-- file now waits until somebody has marked it read.
UPDATE compliancerules SET reviewrequired = 1
 WHERE code = 'GA_NET_BACKGROUND' AND accountid IS NULL AND effectiveto IS NULL;

-- --- Georgia DHS ----------------------------------------------------------------------------------

-- The five-year renewal came over from Florida's Level 2 rule. The DHS manual could not be read to
-- confirm any interval, so the check is owed once until somebody can say otherwise.
UPDATE compliancerules SET recurrence = 'once', recurrencedays = NULL,
       note = 'Renewal interval not established from DHS MAN1425; confirm with DHS before setting one.'
 WHERE code = 'DHS_FINGERPRINT' AND accountid IS NULL AND effectiveto IS NULL;

-- "Verified negative": a screen answers only when its result is recorded negative.
UPDATE compliancerules SET reviewrequired = 1
 WHERE code = 'DHS_PREEMP_DRUG' AND accountid IS NULL AND effectiveto IS NULL;
