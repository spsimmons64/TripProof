-- The five obligations the audit found with no rule at all.
--
-- Each is a duty on the CARRIER rather than on a driver, which is how they came to be missed:
-- the driver file was built first and built thoroughly, and these live outside it.

-- 1. THE ACCIDENT REGISTER - 49 CFR 390.15(b)
--
-- Not a document. A list the carrier keeps for three years, and 390.15(b)(1) says what each
-- entry must carry: the date, the city or town and State, the driver, the number injured, the
-- number killed, and whether hazardous material other than fuel from the vehicles' own tanks
-- was released. Every one of those is already a column on driveraccidents, so the rule reads
-- the accidents rather than asking anybody to produce a register separately - and an empty
-- register is a complete one, which it says rather than going red at a carrier that has had
-- no accidents.
INSERT INTO compliancerules
  (recordid, accountid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, sourceurl, applieswhen, evidencekind, evidencesource, origin, extendable, blocking,
   gate, grouping, duestage, duetext, recurrence, warndays, sensitivity, retentionrule,
   effectivefrom, sortorder)
SELECT UUID(), NULL, 'ACCIDENT_REGISTER', 'Accident register',
       CONCAT('A list of every accident, kept for three years after each one. For each: the ',
              'date, the city or town and the State, the driver, how many people were injured, ',
              'how many were killed, and whether hazardous material other than fuel from the ',
              'vehicles'' own tanks was released. Nothing is uploaded - the register is the ',
              'accidents recorded against this company''s drivers, and it is short only where ',
              'one of them is missing a particular the rule asks for.'),
       'company', 'regulation', 'FMCSA', 'US', '49 CFR 390.15(b)',
       'https://www.ecfr.gov/current/title-49/section-390.15',
       '{"all":[{"fact":"operation.interstate","is":true},{"any":[{"fact":"company.cmvdrivers","is":true},{"fact":"fleet.cmv_federal","is":true}]}]}',
       'process', 'accidentregister', 'office', 0, 1,
       'deficiency', 'regulatory', 'ongoing',
       'Kept for three years after each accident',
       'once', 30, 'normal', 'Held 3 years - 49 CFR 390.15(b)(2)', '1970-01-01', 70
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'ACCIDENT_REGISTER');

-- 2. USDOT NUMBER AND OPERATING AUTHORITY
--
-- The number everything else is filed against - the MCS-150 schedule is computed from its last
-- two digits, so TripProof was using it while never requiring it. Carrying passengers for hire
-- across a State line needs FMCSA operating authority as well, which is a separate grant.
INSERT INTO compliancerules
  (recordid, accountid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, sourceurl, applieswhen, evidencekind, evidencesource, origin, extendable, blocking,
   gate, grouping, duestage, duetext, recurrence, warndays, sensitivity, effectivefrom, sortorder)
SELECT UUID(), NULL, 'USDOT_AUTHORITY', 'USDOT number and operating authority',
       CONCAT('Every motor carrier operating a commercial motor vehicle in interstate commerce ',
              'needs a USDOT number. A carrier transporting passengers FOR HIRE across a State ',
              'line needs FMCSA operating authority as well - an MC number - which is granted ',
              'separately and requires proof of insurance on file with FMCSA. Both are held on ',
              'the company record rather than as documents, because that is where the rest of ',
              'TripProof reads them from.'),
       'company', 'regulation', 'FMCSA', 'US', '49 CFR 390.19; 49 CFR 365.101',
       'https://www.fmcsa.dot.gov/registration',
       '{"fact":"operation.interstate","is":true}',
       'process', 'usdotnumber', 'office', 0, 1,
       'hardstop', 'regulatory', 'ongoing', 'Before operating in interstate commerce',
       'once', 30, 'normal', '1970-01-01', 1
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'USDOT_AUTHORITY');

-- 3. UNIFIED CARRIER REGISTRATION - annual
INSERT INTO credentialtypes (recordid, accountid, code, name, subject, category, description, active)
SELECT UUID(), NULL, 'UCR_REGISTRATION', 'Unified Carrier Registration', 'company', 'registration',
       'The UCR receipt for the registration year. Renewed annually.', 1
 WHERE NOT EXISTS (SELECT 1 FROM credentialtypes WHERE code = 'UCR_REGISTRATION');

INSERT INTO compliancerules
  (recordid, accountid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, sourceurl, applieswhen, evidencekind, evidencesource, origin, extendable, blocking,
   gate, grouping, duestage, duetext, recurrence, recurrencedays, warndays, sensitivity,
   effectivefrom, sortorder)
SELECT UUID(), NULL, 'UCR', 'Unified Carrier Registration',
       CONCAT('An annual registration and fee for motor carriers operating in interstate ',
              'commerce, paid through the UCR system and based on fleet size. It is separate ',
              'from the USDOT number and from the biennial MCS-150 update, and a carrier that ',
              'has done those two has not done this one.'),
       'company', 'regulation', 'FMCSA', 'US', '49 U.S.C. 14504a',
       'https://www.ucr.gov/',
       '{"fact":"operation.interstate","is":true}',
       'document', 'credential:UCR_REGISTRATION', 'office', 0, 1,
       'deficiency', 'regulatory', 'ongoing', 'Renewed every year',
       'days', 365, 45, 'normal', '2007-09-10', 61
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'UCR');

-- 4. MCS-90B ENDORSEMENT - 49 CFR 387.39
--
-- The minimum cover is already asked for. This is the endorsement attached to the policy that
-- makes the insurer answerable to the public for it - a carrier can hold a compliant policy and
-- still be short of 387 without it.
INSERT INTO credentialtypes (recordid, accountid, code, name, subject, category, description, active)
SELECT UUID(), NULL, 'MCS90B', 'MCS-90B endorsement', 'company', 'insurance',
       'The endorsement attached to the liability policy, in the form 49 CFR 387.39 prescribes '
       'for passenger carriers.', 1
 WHERE NOT EXISTS (SELECT 1 FROM credentialtypes WHERE code = 'MCS90B');

INSERT INTO compliancerules
  (recordid, accountid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, sourceurl, applieswhen, evidencekind, evidencesource, origin, extendable, blocking,
   gate, grouping, duestage, duetext, recurrence, warndays, sensitivity, effectivefrom, sortorder)
SELECT UUID(), NULL, 'MCS90B', 'MCS-90B endorsement on the liability policy',
       CONCAT('The endorsement that makes the insurer answerable to the public for the minimum ',
              'cover 49 CFR 387.33 requires, in the form prescribed for passenger carriers. It ',
              'is not the policy and it is not the certificate: a carrier can hold a compliant ',
              'policy, have the certificate on file, and still be short of Part 387 because the ',
              'endorsement was never attached.'),
       'company', 'regulation', 'FMCSA', 'US', '49 CFR 387.39; 49 CFR 387.31',
       'https://www.ecfr.gov/current/title-49/section-387.39',
       '{"fact":"operation.interstate","is":true}',
       'document', 'credential:MCS90B', 'office', 0, 1,
       'deficiency', 'regulatory', 'ongoing', 'For as long as the policy is in force',
       'ondocument', 30, 'normal', '1970-01-01', 6
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'MCS90B');

-- 5. DRUG AND ALCOHOL MIS REPORT - 49 CFR 382.403
--
-- Owed only when FMCSA asks in writing, which is why it needs a question rather than a trigger
-- read off the data: nothing in TripProof can know a letter arrived.
INSERT INTO companyquestions (code, factname, question, help, sortorder, active)
SELECT 'MIS_REQUESTED', 'company.misrequested',
       'Has FMCSA asked this company in writing for a drug and alcohol MIS report?',
       'Only carriers notified in writing have to file one. 49 CFR 382.403.', 90, 1
 WHERE NOT EXISTS (SELECT 1 FROM companyquestions WHERE factname = 'company.misrequested');

INSERT INTO credentialtypes (recordid, accountid, code, name, subject, category, description, active)
SELECT UUID(), NULL, 'DA_MIS_REPORT', 'Drug and alcohol MIS report', 'company', 'testing',
       'The submitted MIS report for the calendar year FMCSA asked about.', 1
 WHERE NOT EXISTS (SELECT 1 FROM credentialtypes WHERE code = 'DA_MIS_REPORT');

INSERT INTO compliancerules
  (recordid, accountid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, sourceurl, applieswhen, evidencekind, evidencesource, origin, extendable, blocking,
   gate, grouping, duestage, duetext, recurrence, recurrencedays, warndays, sensitivity,
   retentionrule, effectivefrom, sortorder)
SELECT UUID(), NULL, 'DA_MIS_REPORT', 'Drug and alcohol MIS report',
       CONCAT('The annual summary of testing results for the preceding calendar year, owed ',
              'ONLY by a carrier FMCSA has notified in writing. It is not a universal ',
              'obligation and most carriers are never asked - but one that is asked and does ',
              'not file is in violation, and nothing in a records system can know the letter ',
              'arrived unless somebody says so.'),
       'company', 'regulation', 'FMCSA', 'US', '49 CFR 382.403',
       'https://www.ecfr.gov/current/title-49/section-382.403',
       '{"fact":"company.misrequested","is":true}',
       'document', 'credential:DA_MIS_REPORT', 'office', 0, 1,
       'deficiency', 'regulatory', 'ongoing', 'By 15 March, for the preceding calendar year',
       'days', 365, 30, 'normal', '5 years - 49 CFR 382.401(b)', '2001-08-01', 17
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'DA_MIS_REPORT');
