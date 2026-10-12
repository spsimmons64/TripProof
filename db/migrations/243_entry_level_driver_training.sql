-- Entry-level driver training - 49 CFR Part 380 Subpart F.
--
-- The engine already KNEW about this: the endorsement rule's failure text says a first P, S or H
-- endorsement needs entry-level training first. It just never asked for it. A requirement the
-- software can name but cannot check is one an operator finds out about from a state examiner.
--
-- It is tied to GETTING the licence or endorsement, not to being hired. A driver who has held a
-- Class B since 2019 does not repeat it because a new company took them on in 2026 - but that
-- same driver taking a Passenger endorsement for the first time in 2026 does, even though their
-- CDL predates the rule. So this is read off the licensing history rather than asked of every
-- CDL holder, and `driver.eldt` is what reads it:
--
--   not asked   every CDL class and P/S/H endorsement on file was issued before 07/02/2022
--   asked       one of them was issued on or after it
--   undecided   no licence is recorded, so there is no history to read - an empty licensing
--               history is not evidence of an exemption
--
-- Evidence is the Training Provider Registry record or the completion documentation - and
-- equally, the licence history that establishes the exemption, which is why the credential takes
-- either. The state verified the training before it issued the licence; what this asks of the
-- carrier is that it can show which of the two is true.

INSERT INTO credentialtypes (recordid, accountid, code, name, subject, category, description, active)
SELECT UUID(), NULL, 'ELDT', 'Entry-level driver training', 'driver', 'training',
       'The Training Provider Registry record or the provider''s completion documentation - or '
       'the licence history showing the class or endorsement was held before 7 February 2022, '
       'which is an exemption rather than a completion. Record the provider.', 1
 WHERE NOT EXISTS (SELECT 1 FROM credentialtypes WHERE code = 'ELDT');

INSERT INTO compliancerules
  (recordid, accountid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, sourceurl, applieswhen, evidencekind, evidencesource, origin, extendable, blocking,
   gate, grouping, duestage, duetext, recurrence, warndays, sensitivity, retentionrule,
   effectivefrom, sortorder)
SELECT UUID(), NULL, 'ELDT', 'Entry-level driver training verification',
       CONCAT('Required before the skills test for a first Class A or Class B CDL, an upgrade ',
              'from Class B to Class A, or a first Passenger, School Bus or Hazardous Materials ',
              'endorsement. It belongs to the licence, not to the job: a driver who has held ',
              'the class since before 7 February 2022 does not repeat it on being hired, but a ',
              'driver taking a Passenger endorsement for the first time now does, whatever the ',
              'age of their CDL. The training is given by an organisation on FMCSA''s Training ',
              'Provider Registry, which reports completion to the registry electronically. What ',
              'is kept here is the registry record, the completion documentation, or the licence ',
              'history that shows the exemption.'),
       'driver', 'regulation', 'FMCSA', 'US', '49 CFR 380.603; 49 CFR 380.609',
       'https://tpr.fmcsa.dot.gov/',
       '{"fact":"driver.eldt","is":true}',
       'document', 'credential:ELDT', 'thirdparty', 0, 1,
       'deficiency', 'regulatory', 'prehire',
       'Before the skills or endorsement test the licence was issued on',
       'once', 30, 'normal',
       'Held for the duration of employment plus 3 years - 49 CFR 391.51',
       '2022-02-07', 118
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'ELDT');
