-- Bloodborne pathogens, with the two company obligations the driver requirement hangs off.
--
-- WHAT WAS ALREADY RIGHT: the training is asked only where `company.exposure` is true, so it was
-- never on every driver's list regardless of duties. That gate stays exactly as it is.
--
-- WHAT WAS MISSING: the company side. 29 CFR 1910.1030 asks the employer for two written things
-- BEFORE any of this reaches a driver, and TripProof asked for neither:
--
--   (c)(2)  an exposure determination - which job classifications, and which tasks within them,
--           have occupational exposure. Made without regard to personal protective equipment:
--           the question is what the job involves, not what the driver is wearing while doing it.
--   (c)(1)  a written exposure control plan, reviewed and updated at least annually and whenever
--           new tasks or procedures affect exposure.
--
-- A company answering "yes, driver duties make blood exposure foreseeable" in Settings has made
-- that determination in substance. OSHA asks for it in writing, listing the classifications and
-- tasks, and asks for the plan that follows from it. Both are now asked for, and both only where
-- the company has said exposure exists - a company with no occupational exposure owes neither.
--
-- WHAT WAS WRONG ON THE DRIVER RULE:
--   * The citation was the whole section. The training obligation is (g)(2).
--   * It was due "within 30 days of hire". 1910.1030(g)(2)(i) ties it to the work, not the
--     payroll: at the time of INITIAL ASSIGNMENT to tasks where occupational exposure may take
--     place, and annually within one year of the previous training. A driver hired into an
--     office job and moved onto exposure duties six months later owes it then, not on day 30.
--   * It was called a certificate. OSHA issues none and approves no course. The employer is
--     responsible for providing the training, at no cost to the employee and during working
--     hours, and what is kept is a RECORD - 1910.1030(h)(2)(i) says what has to be in it.

-- 1. The driver requirement, said accurately.
UPDATE compliancerules
   SET citation = '29 CFR 1910.1030(g)(2)',
       description = CONCAT(
         'Training for a driver whose duties make contact with blood or other potentially ',
         'infectious material reasonably foreseeable. The employer provides it, at no cost to ',
         'the driver and during working hours; OSHA approves no course and issues no ',
         'certificate, and the trainer must be knowledgeable about the subject as it applies to ',
         'this workplace. What is kept is the training record: the date, a summary of what was ',
         'covered, the name and qualifications of the trainer, and the names and job titles of ',
         'everybody who attended - 29 CFR 1910.1030(h)(2)(i).'),
       duedays = NULL,
       duetext = 'At initial assignment to exposure duties, then within one year of the last'
 WHERE code = 'BBP_TRAINING';

UPDATE credentialtypes
   SET name = 'Bloodborne pathogens training record',
       description = 'The date, a summary of what was covered, the name and qualifications of '
                     'the trainer, and who attended. A third-party certificate can form part of '
                     'it. Held three years - 29 CFR 1910.1030(h)(2)(ii).'
 WHERE code = 'BLOODBORNE_PATHOGENS';

-- 2. The two company obligations, as things that can be filed.
INSERT INTO credentialtypes (recordid, accountid, code, name, subject, category, description, active)
SELECT UUID(), NULL, 'BBP_EXPOSURE_DETERMINATION',
       'Bloodborne pathogens exposure determination', 'company', 'safety',
       'The job classifications in which employees have occupational exposure, and the tasks '
       'within them. Made without regard to personal protective equipment.', 1
 WHERE NOT EXISTS (SELECT 1 FROM credentialtypes WHERE code = 'BBP_EXPOSURE_DETERMINATION');

INSERT INTO credentialtypes (recordid, accountid, code, name, subject, category, description, active)
SELECT UUID(), NULL, 'BBP_EXPOSURE_PLAN',
       'Bloodborne pathogens exposure control plan', 'company', 'safety',
       'The written plan for eliminating or minimising exposure. Reviewed and updated at least '
       'annually and whenever new tasks or procedures affect exposure.', 1
 WHERE NOT EXISTS (SELECT 1 FROM credentialtypes WHERE code = 'BBP_EXPOSURE_PLAN');

-- 3. The rules that ask for them. Modelled on HIPAA_RISK_ANALYSIS, which is the same shape: a
--    written thing the office produces, held by the company, owed only where the trigger is true.
INSERT INTO compliancerules
  (recordid, accountid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, sourceurl, applieswhen, evidencekind, evidencesource, origin, extendable, blocking,
   gate, grouping, duestage, duetext, recurrence, recurrencedays, warndays, sensitivity,
   retentionrule, effectivefrom, sortorder)
SELECT UUID(), NULL, 'BBP_EXPOSURE_DETERMINATION',
       'Bloodborne pathogens exposure determination',
       CONCAT('A written list of the job classifications in which employees have occupational ',
              'exposure to blood or other potentially infectious material, and of the tasks and ',
              'procedures within those classifications where it occurs. Made WITHOUT regard to ',
              'personal protective equipment - the question is what the job involves, not what ',
              'is worn while doing it. This determination is what decides which drivers owe the ',
              'training, so it comes before any of them.'),
       'company', 'regulation', 'OSHA', 'US', '29 CFR 1910.1030(c)(2)',
       'https://www.ecfr.gov/current/title-29/section-1910.1030',
       '{"fact":"company.exposure","is":true}',
       'document', 'credential:BBP_EXPOSURE_DETERMINATION', 'office', 0, 1,
       'deficiency', 'regulatory', 'ongoing',
       'Before anybody is assigned to work with occupational exposure',
       'ondocument', NULL, 30, 'normal',
       'Held with the exposure control plan', '1992-03-06', 67
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'BBP_EXPOSURE_DETERMINATION');

INSERT INTO compliancerules
  (recordid, accountid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, sourceurl, applieswhen, evidencekind, evidencesource, origin, extendable, blocking,
   gate, grouping, duestage, duetext, recurrence, recurrencedays, warndays, sensitivity,
   retentionrule, effectivefrom, sortorder)
SELECT UUID(), NULL, 'BBP_EXPOSURE_PLAN',
       'Bloodborne pathogens exposure control plan',
       CONCAT('The written plan for eliminating or minimising employee exposure, covering the ',
              'exposure determination, the methods of compliance, hepatitis B vaccination, ',
              'what happens after an exposure incident, communication of hazards, and ',
              'recordkeeping. Reviewed and updated at least annually, and whenever new or ',
              'modified tasks and procedures affect occupational exposure.'),
       'company', 'regulation', 'OSHA', 'US', '29 CFR 1910.1030(c)(1)',
       'https://www.ecfr.gov/current/title-29/section-1910.1030',
       '{"fact":"company.exposure","is":true}',
       'document', 'credential:BBP_EXPOSURE_PLAN', 'office', 0, 1,
       'deficiency', 'regulatory', 'ongoing',
       'Reviewed and updated at least annually',
       'days', 365, 30, 'normal',
       'Kept current; superseded versions held three years', '1992-03-06', 68
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'BBP_EXPOSURE_PLAN');
