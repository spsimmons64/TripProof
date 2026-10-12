-- ################################################################################################
-- # 106 - the first driver rules, as data.
-- #
-- # These are rows, not code. Each one says where it comes from, when it reaches a driver, and what
-- # would answer it. Adding the next rule is an INSERT; it is never a new column and never a patch
-- # to the evaluator.
-- #
-- # `evidencesource` says where to look for the answer, as "<kind>" or "<kind>:<which>". The kinds
-- # are handled in rules.py because there are only seven shapes a record can have; the `which` is
-- # data. Nothing is copied - the MVR's state lives in drivermvrs and is read from there.
-- #
-- # WHAT IS SEEDED HERE, AND WHAT IS NOT. Only rules that can be decided from facts the application
-- # actually collects today: the vehicle measurements (105) and whether the company drives across a
-- # state line (105). That is the federal baseline, Part 391, Part 382 and the Florida intrastate
-- # inversion - enough to prove the mechanism end to end against a real fleet.
-- #
-- # The conditional overlays from the matrix - Medicaid exclusion screening, Level 1 screening,
-- # HIPAA, wheelchair securement, Chapter 14-90, the CTC programme - are deliberately NOT here.
-- # Each needs a company-level question that has no field yet, and a rule that silently evaluates
-- # against a fact nobody has recorded is worse than an absent rule: it reads as an answer.
-- #
-- # THE INVERSION IS THE POINT. Read FED_PART391_* against FL_INTRASTATE_382. Interstate, a
-- # commercial motor vehicle brings the qualification file and no drug programme. Intrastate in
-- # Florida under 26,001 lb, F.S. 316.302(2)(f) drops the qualification file and requires the drug
-- # programme instead. Same van, opposite obligations, and both rules are three lines of JSON.
-- ################################################################################################

ALTER TABLE compliancerules
    ADD COLUMN IF NOT EXISTS evidencesource VARCHAR(64) NULL AFTER evidencekind;


-- ------------------------------------------------------------------------------------------------
-- Everyone, whatever they drive. Employment paperwork and the driver's own licence.
-- ------------------------------------------------------------------------------------------------
INSERT INTO compliancerules
  (recordid, code, name, subject, authoritytype, authority, jurisdiction, citation, applieswhen,
   evidencekind, evidencesource, reviewrequired, determination, blocking, duestage, recurrence,
   recurrencedays, effectivefrom, sortorder)
VALUES
  (UUID(), 'DRIVER_LICENSE_COPY', 'Copy of the driver''s license', 'driver', 'statute', 'CMS', 'US',
   '42 U.S.C. 1396a(a)(87)(B)', NULL, 'document', 'licencecopy', 0, 0, 1, 'prehire', 'ondocument',
   NULL, '2021-12-27', 10),

  (UUID(), 'I9', 'Form I-9', 'driver', 'regulation', 'USCIS', 'US', '8 CFR 274a.2', NULL,
   'document', 'signature:I9', 0, 0, 1, 'athire', 'once', NULL, '1986-11-06', 20),

  (UUID(), 'W4', 'Form W-4', 'driver', 'regulation', 'IRS', 'US', '26 CFR 31.3402(f)(2)-1', NULL,
   'document', 'signature:W4', 0, 0, 0, 'athire', 'once', NULL, '1986-11-06', 30),

  (UUID(), 'MVR_FILE', 'Driving history disclosed to the State', 'driver', 'statute', 'CMS', 'US',
   '42 U.S.C. 1396a(a)(87)(D)', NULL, 'process', 'mvr', 1, 0, 1, 'prehire', 'once', NULL,
   '2021-12-27', 40),


-- ------------------------------------------------------------------------------------------------
-- Part 391, in interstate commerce. Reaches any commercial motor vehicle under 49 CFR 390.5 -
-- a CDL has nothing to do with it, which is the distinction the old catalog could not express.
-- ------------------------------------------------------------------------------------------------
  (UUID(), 'DQ_FILE', 'Driver qualification file', 'driver', 'regulation', 'FMCSA', 'US',
   '49 CFR 391.51',
   '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cmv_federal","is":true}]}',
   'process', NULL, 0, 0, 1, 'ongoing', 'once', NULL, '2000-01-01', 100),

  (UUID(), 'EMPLOYMENT_APPLICATION', 'DOT application for employment', 'driver', 'regulation',
   'FMCSA', 'US', '49 CFR 391.21',
   '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cmv_federal","is":true}]}',
   'document', 'signature:DOT_APPLICATION', 0, 0, 1, 'prehire', 'perhire', NULL, '2000-01-01', 110),

  (UUID(), 'MVR_PREEMPLOYMENT', 'Motor vehicle record at hire', 'driver', 'regulation', 'FMCSA',
   'US', '49 CFR 391.23(a)(1)',
   '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cmv_federal","is":true}]}',
   'document', 'mvr', 1, 0, 1, 'prehire', 'perhire', NULL, '2000-01-01', 120),

  (UUID(), 'SAFETY_PERFORMANCE_CONSENT', 'Consent to release safety performance history', 'driver',
   'regulation', 'FMCSA', 'US', '49 CFR 391.23(g)',
   '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cmv_federal","is":true}]}',
   'document', 'signature:SAFETY_PERFORMANCE_CONSENT', 0, 0, 1, 'prehire', 'perhire', NULL,
   '2000-01-01', 130),

  (UUID(), 'ROAD_TEST', 'Road test certificate or accepted equivalent', 'driver', 'regulation',
   'FMCSA', 'US', '49 CFR 391.31',
   '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cmv_federal","is":true}]}',
   'document', 'credential:ROAD_TEST', 0, 0, 1, 'athire', 'once', NULL, '2000-01-01', 140),

  (UUID(), 'MEDICAL_CERT', 'Medical examiner''s certificate', 'driver', 'regulation', 'FMCSA', 'US',
   '49 CFR 391.43',
   '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cmv_federal","is":true}]}',
   'document', 'credential:DOT_MEDICAL_CARD', 0, 0, 1, 'prehire', 'ondocument', NULL, '2000-01-01', 150),

  (UUID(), 'MVR_ANNUAL', 'Annual inquiry and review of driving record', 'driver', 'regulation',
   'FMCSA', 'US', '49 CFR 391.25',
   '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cmv_federal","is":true}]}',
   'process', 'annualreview', 1, 1, 1, 'ongoing', 'days', 365, '2000-01-01', 160),


-- ------------------------------------------------------------------------------------------------
-- Part 382, which follows the CDL and not the vehicle - 49 CFR 382.103(a)(1). A driver in a
-- fifteen-passenger van is outside it entirely.
-- ------------------------------------------------------------------------------------------------
  (UUID(), 'PREEMPLOYMENT_DRUG_TEST', 'Pre-employment controlled substances test', 'driver',
   'regulation', 'FMCSA', 'US', '49 CFR 382.301',
   '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cdl_required","is":true}]}',
   'test', 'drugtest:preemployment', 0, 1, 1, 'prehire', 'perhire', NULL, '2000-01-01', 200),

  (UUID(), 'CLEARINGHOUSE_PREEMP', 'Clearinghouse pre-employment full query', 'driver', 'regulation',
   'FMCSA', 'US', '49 CFR 382.701(a)',
   '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cdl_required","is":true}]}',
   'query', 'report:CLEARINGHOUSE_PREEMP', 0, 0, 1, 'prehire', 'perhire', NULL, '2020-01-06', 210),

  (UUID(), 'CLEARINGHOUSE', 'Clearinghouse annual limited query', 'driver', 'regulation', 'FMCSA',
   'US', '49 CFR 382.701(b)',
   '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cdl_required","is":true}]}',
   'query', 'report:CLEARINGHOUSE', 0, 0, 1, 'ongoing', 'days', 365, '2020-01-06', 220),

  (UUID(), 'DA_POLICY_RECEIPT', 'Drug and alcohol policy - signed receipt', 'driver', 'regulation',
   'FMCSA', 'US', '49 CFR 382.601(d)',
   '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cdl_required","is":true}]}',
   'document', 'signature:DRUG_POLICY', 0, 0, 1, 'prehire', 'once', NULL, '2000-01-01', 230),


-- ------------------------------------------------------------------------------------------------
-- Florida, intrastate. F.S. 316.302(2)(f) exempts an operator under 26,001 lb running solely
-- within the state from subsection (1) - so Part 391 does NOT apply - and then expressly requires
-- Part 382. The exact inverse of the federal position above, and the case most of an NEMT fleet
-- actually sits in.
--
-- F.S. 316.003(14) has no compensation prong, so a van under 10,000 lb is not a Florida commercial
-- motor vehicle at all and none of this engages, however many seats it has.
-- ------------------------------------------------------------------------------------------------
  (UUID(), 'FL_INTRASTATE_382', 'Drug and alcohol testing programme (Florida intrastate)', 'driver',
   'statute', 'Florida', 'FL', 'F.S. 316.302(2)(f); 49 CFR part 382',
   '{"all":[{"fact":"operation.interstate","is":false},{"fact":"fleet.cmv_florida","is":true},{"fact":"fleet.heaviest_gvwr","lt":26001}]}',
   'test', 'drugtest:preemployment', 0, 1, 1, 'prehire', 'perhire', NULL, '2024-01-01', 300),

  (UUID(), 'FL_INTRASTATE_FULL', 'Full FMCSR compliance (Florida intrastate, 26,001 lb and over)',
   'driver', 'statute', 'Florida', 'FL', 'F.S. 316.302(1)(b)',
   '{"all":[{"fact":"operation.interstate","is":false},{"fact":"fleet.cmv_florida","is":true},{"fact":"fleet.heaviest_gvwr","gte":26001}]}',
   'process', NULL, 0, 0, 1, 'ongoing', 'once', NULL, '2024-01-01', 310);
