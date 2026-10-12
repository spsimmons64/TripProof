-- ################################################################################################
-- # 186 - say who it came from.
-- #
-- # 184 gave every rule an `origin` saying whether its evidence is made inside this office or
-- # outside it, which is what the engine needs to know. It is not what a person needs to read.
-- # "Came in from outside" is true of a laboratory result, a driver's photograph of a licence, an
-- # examiner's road test and a previous employer's reply, and somebody working a queue is deciding
-- # what to do next - which is a different decision for each of those.
-- #
-- # So the column carries the whole answer instead of half of it. One column, because two - a
-- # yes/no for the gate and a word for the sentence - is two things to keep in step, and they
-- # would not stay in step.
-- #
-- #   office      this office made it. Nobody else to check after, and it never goes to review.
-- #   driver      the driver sent it: a signature, an application answer, a copy of their licence,
-- #               their own duty records.
-- #   examiner    somebody who examined them: a medical examiner, a road test examiner.
-- #   employer    a previous employer answering a safety performance inquiry.
-- #   thirdparty  a laboratory, a licensing authority, a federal database, a training provider.
-- ################################################################################################

ALTER TABLE compliancerules MODIFY COLUMN origin VARCHAR(12) NOT NULL DEFAULT 'thirdparty';

UPDATE compliancerules SET origin = 'thirdparty' WHERE subject = 'driver' AND origin = 'outside';

UPDATE compliancerules
   SET origin = 'driver'
 WHERE subject = 'driver'
   AND (evidencesource LIKE 'signature:%'
        OR evidencesource LIKE 'applicationanswer%'
        OR evidencesource = 'licencecopy'
        OR evidencesource = 'credential:DUTY_STATUS_RECORD');

UPDATE compliancerules
   SET origin = 'examiner'
 WHERE subject = 'driver'
   AND evidencesource IN ('roadtest', 'transitmedical', 'credential:DOT_MEDICAL_CARD');

UPDATE compliancerules
   SET origin = 'employer'
 WHERE subject = 'driver' AND evidencesource = 'employerhistory';

UPDATE compliancerules
   SET origin = 'office'
 WHERE subject = 'driver'
   AND (evidencesource IS NULL OR evidencesource IN ('annualreview', 'poolmember'));
