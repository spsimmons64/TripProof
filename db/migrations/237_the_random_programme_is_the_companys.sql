-- The random testing PROGRAMME is the company's obligation.
--
-- 49 CFR 382.305 is addressed to the employer: it must operate, or take part in, a compliant
-- random drug and alcohol testing programme for the drivers Part 382 covers. It does NOT require
-- anybody to join an outside pool - a company may run its own selections, or enrol with a
-- consortium / third-party administrator, and either satisfies it.
--
-- TripProof had the two halves that hang off that programme and not the programme itself:
--
--   RANDOM_TESTING_RECORDS  (driver)   is this driver in the pool
--   RANDOM_SELECTIONS       (company)  were the draws made, at the right rate, spread out
--
-- Both stay. The per-driver membership is worth tracking exactly as it is - it is how you know
-- the pool holds the right people - and the selections are the other half. What was missing is
-- the thing they both belong to: evidence that a programme exists at all, which is the C/TPA
-- enrolment or the company's own written selection procedure.
--
-- AND IT DOES NOT GO GREEN AND STAY GREEN. That is the point of answering it from
-- `randomprogram` rather than from the document alone: an enrolment with no selection drawn in
-- the last twelve months reads as enrolled, not as compliant. A pool nobody draws from tests
-- nobody, and the rate in 382.305 is met across a year, not by signing up once.

INSERT INTO credentialtypes (recordid, accountid, code, name, subject, category, description, active)
SELECT UUID(), NULL, 'RANDOM_TESTING_PROGRAM',
       'DOT random testing program', 'company', 'testing',
       'Enrolment with a consortium or third-party administrator, or the company''s own written '
       'random selection procedure. Record the administrator under the provider.', 1
 WHERE NOT EXISTS (SELECT 1 FROM credentialtypes WHERE code = 'RANDOM_TESTING_PROGRAM');

INSERT INTO compliancerules
  (recordid, accountid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, sourceurl, applieswhen, evidencekind, evidencesource, origin, extendable, blocking,
   gate, grouping, duestage, duetext, recurrence, warndays, sensitivity, retentionrule,
   effectivefrom, sortorder)
SELECT UUID(), NULL, 'RANDOM_TESTING_PROGRAM',
       'DOT random drug and alcohol testing program',
       CONCAT('The employer must operate, or take part in, a random testing programme covering ',
              'every driver Part 382 reaches. It may run its own pool and selections, or enrol ',
              'with a consortium or third-party administrator - nothing requires an outside ',
              'pool. Evidence is the enrolment, or the company''s own written selection ',
              'procedure. This is not answered by the paperwork alone: a programme with no ',
              'selection drawn from it in the last twelve months is an enrolment, not a '
              'testing programme.'),
       'company', 'regulation', 'FMCSA', 'US', '49 CFR 382.305',
       'https://www.ecfr.gov/current/title-49/section-382.305',
       '{"all":[{"fact":"operation.interstate","is":true},{"any":[{"fact":"company.cdldrivers","is":true},{"fact":"fleet.cdl_required","is":true}]}]}',
       'document', 'randomprogram', 'office', 0, 1,
       'deficiency', 'regulatory', 'ongoing',
       'In force while any driver Part 382 covers is employed',
       'ondocument', 30, 'normal',
       '5 years - 49 CFR 382.401(b)', '2000-01-01', 14
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'RANDOM_TESTING_PROGRAM');
