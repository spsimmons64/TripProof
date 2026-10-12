-- ################################################################################################
-- # 215 - the insurance a NEMT operator carries, asked for at last.
-- #
-- # Five company credential types have existed since early on - commercial auto liability, general
-- # liability, workers' compensation, hired and non-owned auto, abuse and molestation - and not one
-- # compliance rule has ever pointed at any of them. A company could carry no insurance at all, or
-- # let every policy lapse, and nothing anywhere in TripProof would say a word. In this industry
-- # that was the largest hole in the application.
-- #
-- # They are not all the same kind of obligation and the rows say which is which:
-- #
-- #   AUTO LIABILITY is law. 49 CFR 387.33 sets the minimum for a for-hire carrier of passengers in
-- #   interstate commerce at $5,000,000 where the vehicle seats 16 or more including the driver and
-- #   $1,500,000 where it seats 15 or fewer. Intrastate limits are the State's. Either way no
-- #   vehicle is lawfully operated for hire without it, so this one is a hard stop.
-- #
-- #   WORKERS' COMPENSATION is State law, on thresholds each State sets.
-- #
-- #   GENERAL LIABILITY, HIRED AND NON-OWNED AUTO and ABUSE AND MOLESTATION are contract, not
-- #   statute. Brokers and payers require them; the authority line says so rather than dressing a
-- #   contract term as a regulation.
-- #
-- # Expiry comes off the certificate itself - a COI carries its own dates - so nothing here invents
-- # a renewal period.
-- #
-- # NOT DONE HERE: the limits carried. A certificate on file with the wrong limit on it satisfies
-- # these rows, because TripProof records the document and not the numbers inside it.
-- ################################################################################################

INSERT INTO companyquestions (code, factname, question, help, sortorder) VALUES
 ('HIRED_AUTOS', 'company.hiredautos',
  'Do drivers ever drive vehicles the company does not own - their own, hired or borrowed?',
  'Hired and non-owned auto cover answers for a vehicle the company does not own but directs the '
  'use of. Where no such vehicle is ever used the cover is not asked for.', 45)
ON DUPLICATE KEY UPDATE active = 1;

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype,
                             authority, citation, applieswhen, evidencekind, evidencesource,
                             origin, extendable, reviewrequired, determination, blocking, gate,
                             grouping, duestage, duetext, recurrence, warndays, note, sortorder,
                             effectivefrom)
SELECT UUID(), 'company', 'AUTO_LIABILITY', 'Commercial auto liability insurance',
       'No vehicle is lawfully operated for hire without it. For a for-hire carrier of passengers '
       'in interstate commerce 49 CFR 387.33 sets the minimum at $5,000,000 where the vehicle '
       'seats 16 or more including the driver, and $1,500,000 where it seats 15 or fewer. An '
       'intrastate operation is held to its own State''s limits, and a broker contract commonly '
       'asks for more than either. TripProof records the certificate and its expiry; it does not '
       'read the limits off it.',
       'regulation', 'FMCSA and State law', '49 CFR 387.31; 49 CFR 387.33', NULL,
       'document', 'credential:AUTO_LIABILITY_COI', 'office', 0, 0, 0, 1, 'hardstop', 'regulatory',
       'ongoing', 'Before any vehicle carries a passenger for hire', 'ondocument', 30, NULL, 5,
       CURRENT_DATE
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules
                    WHERE subject = 'company' AND code = 'AUTO_LIABILITY' AND effectiveto IS NULL);

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype,
                             authority, citation, applieswhen, evidencekind, evidencesource,
                             origin, extendable, reviewrequired, determination, blocking, gate,
                             grouping, duestage, duetext, recurrence, warndays, note, sortorder,
                             effectivefrom)
SELECT UUID(), 'company', 'WORKERS_COMP', 'Workers'' compensation insurance',
       'Required of employers by State law, on thresholds each State sets - Texas is the only '
       'State where a private employer may decline it, and a transportation contract will usually '
       'require it there regardless. The certificate and its expiry are what is kept.',
       'regulation', 'State law', 'State workers'' compensation law', NULL,
       'document', 'credential:WORKERS_COMP_COI', 'office', 1, 0, 0, 1, 'deficiency', 'regulatory',
       'ongoing', NULL, 'ondocument', 30, NULL, 6, CURRENT_DATE
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules
                    WHERE subject = 'company' AND code = 'WORKERS_COMP' AND effectiveto IS NULL);

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype,
                             authority, citation, applieswhen, evidencekind, evidencesource,
                             origin, extendable, reviewrequired, determination, blocking, gate,
                             grouping, duestage, duetext, recurrence, warndays, note, sortorder,
                             effectivefrom)
SELECT UUID(), 'company', 'GENERAL_LIABILITY', 'General liability insurance',
       'Not a regulation. Brokers, payers and facilities require it as a term of doing business, '
       'and a lapse is usually a breach of those contracts rather than of a statute.',
       'contract', 'Broker and payer contracts', NULL, NULL,
       'document', 'credential:GENERAL_LIABILITY_COI', 'office', 1, 0, 0, 1, 'deficiency',
       'company', 'ongoing', NULL, 'ondocument', 30, NULL, 7, CURRENT_DATE
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules
                    WHERE subject = 'company' AND code = 'GENERAL_LIABILITY' AND effectiveto IS NULL);

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype,
                             authority, citation, applieswhen, evidencekind, evidencesource,
                             origin, extendable, reviewrequired, determination, blocking, gate,
                             grouping, duestage, duetext, recurrence, warndays, note, sortorder,
                             effectivefrom)
SELECT UUID(), 'company', 'HNOA', 'Hired and non-owned auto cover',
       'Answers for a vehicle the company does not own but directs the use of - a driver''s own '
       'car, a hired van, a borrowed vehicle. The commercial auto policy on the fleet does not '
       'reach these.',
       'contract', 'Broker and payer contracts', NULL,
       '{"fact":"company.hiredautos","is":true}',
       'document', 'credential:HNOA_COVERAGE', 'office', 1, 0, 0, 1, 'deficiency', 'company',
       'ongoing', NULL, 'ondocument', 30, NULL, 8, CURRENT_DATE
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules
                    WHERE subject = 'company' AND code = 'HNOA' AND effectiveto IS NULL);

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype,
                             authority, citation, applieswhen, evidencekind, evidencesource,
                             origin, extendable, reviewrequired, determination, blocking, gate,
                             grouping, duestage, duetext, recurrence, warndays, note, sortorder,
                             effectivefrom)
SELECT UUID(), 'company', 'ABUSE_MOLESTATION', 'Abuse and molestation cover',
       'Commonly required of a carrier transporting passengers who are elderly, disabled or '
       'otherwise vulnerable, and commonly excluded from a general liability policy, which is why '
       'it is asked for separately. A contract term rather than a regulation.',
       'contract', 'Broker and payer contracts', NULL, NULL,
       'document', 'credential:ABUSE_MOLESTATION_COVERAGE', 'office', 1, 0, 0, 1, 'deficiency',
       'company', 'ongoing', NULL, 'ondocument', 30, NULL, 9, CURRENT_DATE
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules
                    WHERE subject = 'company' AND code = 'ABUSE_MOLESTATION' AND effectiveto IS NULL);
