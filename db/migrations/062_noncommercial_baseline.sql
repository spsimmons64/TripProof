-- ################################################################################################
-- # 062 - the non-commercial NEMT driver's baseline, corrected.
-- #
-- # Read for an ordinary Florida Medicaid NEMT driver who is not operating a commercial motor
-- # vehicle. What is left flatly required is the federal Medicaid minimum driver framework and the
-- # forms every employee signs; everything else names the condition that turns it on.
-- ################################################################################################

-- 49 CFR 391.21 is a Part 391 requirement, and Part 391 reaches a driver of a commercial motor
-- vehicle. An application is still wanted from everyone - that is the company's own practice, and
-- TripProof collects one - but it is not this regulation asking.
UPDATE compliancedocs
   SET obligation = 'conditional', classification = 'conditional', requiredfor = 'cdl',
       appliesif  = 'The driver operates a commercial motor vehicle as Part 391 defines it',
       whendue    = 'Before the driver is employed',
       retention  = 'Three years after employment ends (49 CFR 391.51)',
       description = 'The three-year employment history Part 391 asks for. A non-commercial NEMT driver is '
                     'outside this rule; the company may still take an application as its own practice.'
 WHERE subject = 'driver' AND code = 'EMPLOYMENT_APPLICATION';

-- 37.173 asks for personnel to be trained to proficiency, appropriate to their duties. It names no
-- course and sets no expiry, so neither do we.
UPDATE compliancedocs
   SET obligation = 'conditional', classification = 'conditional',
       name       = 'Passenger assistance and equipment proficiency training',
       appliesif  = 'The driver operates accessible equipment, or assists passengers with disabilities, for a '
                    'covered transportation entity',
       renewal    = 'No interval is set; refresh as duties or equipment change',
       whendue    = 'Before performing the duties it covers',
       validdays  = NULL, expires = 0,
       description = 'Trained to proficiency, appropriate to their duties, in operating the equipment safely '
                     'and in properly assisting and treating individuals with disabilities. The rule names no '
                     'particular course and sets no expiry - PASS is one way to meet it, not the requirement.'
 WHERE subject = 'driver' AND code = 'PASS_TRAINING';

-- The obligation is to ensure the driver is not excluded. Monthly is OIG's advice, because the LEIE
-- is republished monthly - it is not an interval any statute sets.
UPDATE compliancedocs
   SET renewal    = 'No interval in law; monthly is advised as the LEIE is republished monthly',
       whendue    = 'Before the driver carries a Medicaid passenger',
       description = 'Check that the driver is not excluded from federal health care programs, against the OIG '
                     'LEIE and SAM.gov. Federal law requires the assurance; no federal statute or regulation '
                     'sets a checking interval, and OIG says as much - monthly is advice, not a rule.'
 WHERE subject = 'driver' AND code = 'EXCLUSION_CHECK_DRIVER';

-- The driving record is part of the Medicaid minimum framework. Rechecking it on a cycle is the
-- company's policy or its contract, not that framework.
UPDATE compliancedocs
   SET renewal    = 'At hire; any recheck cycle is the company''s or the contract''s',
       whendue    = 'Before the driver carries a Medicaid passenger',
       validdays  = NULL,
       description = 'The driving history behind the licence. Required at hire under the federal Medicaid '
                     'minimum driver framework; how often it is pulled again is set by company policy, a '
                     'broker or a payer, not by that framework.'
 WHERE subject = 'driver' AND code = 'MVR_FILE';

-- Chapter 14-90 items, conditional on the operation rather than on the driver.
UPDATE compliancedocs
   SET obligation = 'conditional', classification = 'conditional',
       appliesif  = 'The operation, or the vehicle, falls under Florida Chapter 14-90 bus transit requirements',
       whendue    = 'Before driving unsupervised'
 WHERE subject = 'driver' AND code = 'FL_LICENSE_STATUS_NOTICE';

-- Drug and alcohol testing records: a programme reaches this driver, rather than every NEMT driver
-- being in one.
UPDATE compliancedocs
   SET obligation = 'conditional', classification = 'conditional',
       appliesif  = 'The driver is in a testing programme a CTC, a Transportation Disadvantaged contract or '
                    'another applicable programme requires',
       whendue    = 'As the programme requires'
 WHERE subject = 'driver' AND code = 'FL_TD_DRUG_TESTING';

-- FCRA is owed when the report comes from a consumer reporting agency, not when the company checks
-- records itself.
UPDATE compliancedocs
   SET obligation = 'conditional', classification = 'conditional',
       appliesif  = 'A background report is obtained from a consumer reporting agency',
       whendue    = 'Before the report is obtained',
       retention  = 'Kept with the hiring record'
 WHERE subject = 'driver' AND code = 'FCRA_FORMS';

-- Accounts follow the catalog where they have not decided otherwise.
UPDATE accountqualifications q
  JOIN compliancedocs c ON c.code = q.code AND c.subject = 'driver'
   SET q.obligation = c.obligation, q.requiredfor = c.requiredfor, q.expires = c.expires,
       q.validdays = c.validdays
 WHERE q.catalog = 1 AND q.updated IS NULL
   AND q.code IN ('EMPLOYMENT_APPLICATION', 'PASS_TRAINING', 'EXCLUSION_CHECK_DRIVER', 'MVR_FILE',
                  'FL_LICENSE_STATUS_NOTICE', 'FL_TD_DRUG_TESTING', 'FCRA_FORMS');
