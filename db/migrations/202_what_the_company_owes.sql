-- ################################################################################################
-- # 202 - what the COMPANY owes, as rules rather than as a filing cabinet.
-- #
-- # Thirteen company credential types have existed since early on and not one requirement has ever
-- # pointed at them. So a company could store a policy or a certificate and nothing anywhere said
-- # whether it was required, whether it was current, or that it had lapsed. Three documents on
-- # file out of thirteen possible, and no screen that could tell you whether that was a problem.
-- #
-- # The catalog has always had `subject`, and the stages, gates and expiry arithmetic never cared
-- # which subject they were working on. What was missing was rules on the company side and a
-- # function to read them. Both arrive here.
-- #
-- # Two of the seven gaps are deliberately NOT in this migration - supervisor reasonable-suspicion
-- # training and the random testing selections. Neither is a document the company holds: the first
-- # is training a named person completed, the second is a draw with a date and a list. They get
-- # records of their own rather than being bent into credentials.
-- ################################################################################################

-- The credential types these rules read. The others already exist.
INSERT INTO credentialtypes (recordid, code, name, subject, description, active) VALUES
 (UUID(), 'DER_DESIGNATION', 'Designated Employer Representative', 'company',
  'Who in this company may receive test results and remove a driver from safety-sensitive duty.', 1),
 (UUID(), 'TPA_AGREEMENT', 'Consortium or third party administrator agreement', 'company',
  'The agreement with whoever administers the drug and alcohol testing program.', 1),
 (UUID(), 'CLEARINGHOUSE_REGISTRATION', 'Clearinghouse employer registration', 'company',
  'Proof the company is registered with the FMCSA Clearinghouse and who its users are.', 1),
 (UUID(), 'SSPP', 'System Safety Program Plan', 'company',
  'The Florida SSPP, adopted and certified annually by a covered bus operator.', 1),
 (UUID(), 'MCS150', 'MCS-150 biennial update', 'company',
  'The carrier registration update FMCSA requires every two years.', 1)
ON DUPLICATE KEY UPDATE active = 1;

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype, authority,
                             citation, applieswhen, evidencekind, evidencesource, origin,
                             extendable, reviewrequired, determination, blocking, gate, grouping,
                             duestage, duetext, recurrence, recurrencedays, warndays, note,
                             sortorder, effectivefrom)
VALUES
 (UUID(), 'company', 'DER_DESIGNATION', 'Designated Employer Representative',
  'Somebody in this company must be authorised to receive test results from the medical review '
  'officer and to immediately remove a driver from safety-sensitive duty. The role is named in '
  'writing - it is the person a laboratory and an MRO will talk to, and testing cannot be run '
  'without one.',
  'regulation', 'FMCSA', '49 CFR 382.105; 49 CFR 40.3',
  '{"fact":"operation.interstate","is":true}',
  'document', 'credential:DER_DESIGNATION', 'office', 0, 0, 0, 1, 'hardstop', 'regulatory',
  'ongoing', 'Before any testing is carried out', 'once', NULL, 30, NULL, 10, CURRENT_DATE),

 (UUID(), 'company', 'TPA_AGREEMENT', 'Consortium or third party administrator agreement',
  'Where a consortium or third party administrator runs any part of the testing program - the '
  'random pool, the collections, the MRO service - the agreement setting out what they do belongs '
  'on file. The duty to comply stays with the company whoever performs the work.',
  'regulation', 'FMCSA', '49 CFR Part 40 Subpart Q; 49 CFR 382.105',
  '{"fact":"operation.interstate","is":true}',
  'document', 'credential:TPA_AGREEMENT', 'office', 1, 0, 0, 1, 'deficiency', 'regulatory',
  'ongoing', NULL, 'once', NULL, 30, NULL, 20, CURRENT_DATE),

 (UUID(), 'company', 'CLEARINGHOUSE_REGISTRATION', 'Clearinghouse employer registration',
  'The company must be registered with the FMCSA Drug and Alcohol Clearinghouse to run queries and '
  'to report violations. Queries on individual drivers cannot be made without it, and the '
  'violations this company records are reportable through it.',
  'regulation', 'FMCSA', '49 CFR 382.701; 49 CFR 382.705',
  '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cdl_required","is":true}]}',
  'document', 'credential:CLEARINGHOUSE_REGISTRATION', 'office', 0, 0, 0, 1, 'hardstop',
  'regulatory', 'ongoing', NULL, 'once', NULL, 30, NULL, 30, CURRENT_DATE),

 (UUID(), 'company', 'DRUG_ALCOHOL_POLICY', 'Drug and alcohol policy',
  'The written policy and educational materials the company must give every driver before any '
  'testing. Each driver''s signed receipt is tracked on their own file; this is the document they '
  'were given.',
  'regulation', 'FMCSA', '49 CFR 382.601',
  '{"fact":"operation.interstate","is":true}',
  'document', 'credential:DRUG_ALCOHOL_POLICY', 'office', 1, 0, 0, 1, 'deficiency', 'regulatory',
  'ongoing', NULL, 'once', NULL, 30, NULL, 40, CURRENT_DATE),

 (UUID(), 'company', 'SSPP', 'System Safety Program Plan',
  'Florida requires a covered bus operator to adopt a System Safety Program Plan and to certify '
  'compliance with it annually. Two of the driver requirements - the driver selection and training '
  'records, and the hours of service limits - are obligations this plan creates.',
  'regulation', 'FDOT', 'F.A.C. 14-90.004',
  '{"all":[{"fact":"company.state","eq":"FL"},{"fact":"company.transit","is":true}]}',
  'document', 'credential:SSPP', 'office', 1, 0, 0, 1, 'deficiency', 'regulatory',
  'ongoing', 'Certified annually', 'days', 365, 30, NULL, 50, CURRENT_DATE),

 (UUID(), 'company', 'MCS150', 'MCS-150 biennial update',
  'Carrier registration must be updated with FMCSA every two years, on a schedule set by the USDOT '
  'number, whether or not anything has changed. Letting it lapse deactivates the USDOT number.',
  'regulation', 'FMCSA', '49 CFR 390.19',
  '{"fact":"operation.interstate","is":true}',
  'document', 'credential:MCS150', 'office', 1, 0, 0, 1, 'deficiency', 'regulatory',
  'ongoing', 'Every two years', 'days', 730, 60, NULL, 60, CURRENT_DATE);
