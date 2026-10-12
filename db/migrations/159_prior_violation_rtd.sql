-- ################################################################################################
-- # 159 - a disclosed prior violation is answered by paper, not by the driver's word.
-- #
-- # The name first. "Return To Duty For A Disclosed Pre-Employment Violation" reads as though every
-- # applicant owes a return-to-duty process. Almost none do: the requirement only reaches somebody
-- # who answered yes to the 40.25(j) question, and what it asks of them is proof.
-- #
-- # And the proof. The rule was satisfied by `driver.priorrtdcomplete` - which is the applicant
-- # saying, on their own application, that they completed the process. That is the right way to
-- # RAISE the question and the wrong way to close it: 49 CFR 40.25(j) and Part 40 Subpart O ask the
-- # employer not to use the person for safety-sensitive functions until the return-to-duty
-- # requirements have been successfully completed, and an applicant's own account of a process run
-- # by somebody else at another company is not documentation of it.
-- #
-- # So the rule now requires a review: the answer still raises it, and a document filed against it
-- # by the office closes it. Until somebody has the SAP's paperwork in their hand, the requirement
-- # reads "on file, waiting to be reviewed" rather than green.
-- ################################################################################################

UPDATE compliancerules
   SET name = 'Prior DOT Pre-Employment Violation / RTD Verification',
       reviewrequired = 1
 WHERE subject = 'driver' AND code = 'PRIOR_VIOLATION_RTD' AND effectiveto IS NULL;
