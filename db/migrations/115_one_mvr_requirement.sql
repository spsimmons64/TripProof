-- ################################################################################################
-- # 115 - one motor vehicle record requirement, not two.
-- #
-- # MVR_FILE was "Driving history disclosed to the State", cited to 42 U.S.C. 1396a(a)(87)(D). Two
-- # things were wrong with it once the research came back.
-- #
-- # First, it sat on the DRIVER. The statute puts the duty on the PROVIDER: "each such provider has
-- # in place a process to disclose to the State Medicaid program the driving history…". It is a
-- # company obligation with a per-driver artifact, not a thing a driver owes.
-- #
-- # Second, and worse, Florida never built anywhere to disclose TO. Florida's state plan says only
-- # "Florida attests that all the minimum requirements outlined in 1902(a)(87) of the Social
-- # Security Act are met", and SMMC Policy Transmittal 2021-40 pushes the duty onto managed care
-- # plans. There is no AHCA form, report or portal that receives a driving history. In practice the
-- # obligation is discharged by holding an annual MVR and producing it to the broker or plan on
-- # request - which is exactly what the other MVR rule already asks for.
-- #
-- # So two rules were asking for one document, one of them wearing a citation that describes a
-- # process nobody can perform. The Medicaid one is retired and the remaining one is broadened to
-- # every driver, which is what the office wanted anyway: an MVR on file for everybody.
-- #
-- # Retired, not deleted - a trip decided last month was decided against the rules in force then,
-- # and end-dating keeps that readable.
-- ################################################################################################

UPDATE compliancerules
   SET effectiveto = CURRENT_DATE,
       note = 'Retired: duplicated the motor vehicle record requirement. The statutory duty is on '
              'the provider, not the driver, and Florida provides no channel to disclose to - it is '
              'satisfied by holding the MVR and producing it to the broker or plan on request.'
 WHERE code = 'MVR_FILE' AND effectiveto IS NULL;

-- The one that remains reaches every driver, not only those under Part 391. For a commercial
-- driver 49 CFR 391.23(a)(1) sets the terms - every licensing authority, three years back, within
-- 30 days of hire. For everyone else the broker contract does, and the company wants one anyway.
UPDATE compliancerules
   SET name        = 'Motor vehicle record',
       applieswhen = NULL,
       citation    = '49 CFR 391.23(a)(1) where Part 391 applies; broker or company policy otherwise',
       authority   = 'FMCSA / broker',
       recurrence  = 'days',
       recurrencedays = 365
 WHERE code = 'MVR_PREEMPLOYMENT' AND effectiveto IS NULL;
