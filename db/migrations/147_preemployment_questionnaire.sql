-- ################################################################################################
-- # 147 - the pre-employment drug and alcohol questionnaire, 49 CFR 40.25(j).
-- #
-- # The one question no employer and no database can answer: in the last two years, did you fail or
-- # refuse a pre-employment DOT test for a job you applied for and DID NOT GET? Nobody holds a
-- # record of that. The previous-employer investigation cannot reach it, because there was no
-- # previous employer - the person never started. The Clearinghouse holds violations reported by
-- # employers, not tests taken for jobs that never began. So it is asked of the applicant, on their
-- # own application, under their own signature.
-- #
-- # WHAT A "YES" MEANS, AND WHAT IT DOES NOT
-- #
-- # It is not a bar on employment. 40.25(j) read with Part 40 Subpart O bars the person from
-- # performing safety-sensitive functions until the return-to-duty process has been completed - and
-- # the employer must verify that it was. Hiring them is the company's decision; letting them drive
-- # before that process is finished is not.
-- #
-- #   answered no                       satisfied
-- #   answered yes, RTD complete        satisfied
-- #   answered yes, RTD not complete    blocked from safety-sensitive work
-- #   not answered                      nothing decided
-- #
-- # Two rules rather than one, because they are two different failures: an unanswered questionnaire
-- # is an incomplete application, and a disclosed violation with no return to duty behind it is a
-- # driver who may not yet drive.
-- ################################################################################################

INSERT INTO compliancerules
  (recordid, code, name, subject, authoritytype, authority, citation, applieswhen, evidencekind,
   evidencesource, recurrence, duestage, blocking, sortorder, effectivefrom)
SELECT UUID(), 'PREEMP_DA_QUESTIONNAIRE',
       'Pre-employment drug and alcohol questionnaire', 'driver', 'federal', 'DOT',
       '49 CFR 40.25(j)',
       '{"all":[{"fact":"operation.interstate","is":true},{"fact":"driver.cdl","is":true}]}',
       'attestation', 'applicationanswered:priorviolation', 'once', 'prehire', 1, 206, '2024-01-01'
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'PREEMP_DA_QUESTIONNAIRE');

INSERT INTO compliancerules
  (recordid, code, name, subject, authoritytype, authority, citation, applieswhen, evidencekind,
   evidencesource, recurrence, duestage, blocking, sortorder, effectivefrom)
SELECT UUID(), 'PRIOR_VIOLATION_RTD',
       'Return to duty for a disclosed pre-employment violation', 'driver', 'federal', 'DOT',
       '49 CFR 40.25(j); Part 40 Subpart O',
       '{"all":[{"fact":"operation.interstate","is":true},{"fact":"driver.cdl","is":true},'
       '{"fact":"driver.priorviolation","is":true}]}',
       'attestation', 'applicationanswer:priorrtdcomplete', 'once', 'predrive', 1, 207, '2024-01-01'
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'PRIOR_VIOLATION_RTD');
