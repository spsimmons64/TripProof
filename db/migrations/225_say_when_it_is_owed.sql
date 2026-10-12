-- ################################################################################################
-- # 225 - say what the follow-up schedule is, not just that nothing is on file.
-- #
-- # A driver who returned to duty had the requirement read "Nothing on file yet." That is true and
-- # it is useless: the office had just completed the return-to-duty process and read it as TripProof
-- # failing to notice. What is actually owed is the thing nobody was told - the SAP prescribes a
-- # schedule of unannounced follow-up tests, at least six in the first twelve months, and the
-- # return-to-duty test is not one of them.
-- #
-- # `duetext` already exists for exactly this and now prints beside the status, so this is a wording
-- # change on three rules rather than a new idea.
-- ################################################################################################

-- The column was sized for a phrase, and these are sentences.
ALTER TABLE compliancerules MODIFY COLUMN duetext VARCHAR(255) NULL;

UPDATE compliancerules
   SET duetext = 'At least six unannounced tests in the first twelve months after return to duty, '
                 'on the schedule the SAP set - the return-to-duty test is not one of them'
 WHERE subject = 'driver' AND code = 'FOLLOWUP_TESTING' AND effectiveto IS NULL;

UPDATE compliancerules
   SET duetext = 'Every twelve months, on the driving record of every licence the driver holds'
 WHERE subject = 'driver' AND code = 'MVR_ANNUAL' AND effectiveto IS NULL;

UPDATE compliancerules
   SET duetext = 'As soon as practicable after the accident - eight hours for alcohol, thirty-two '
                 'for controlled substances'
 WHERE subject = 'driver' AND code = 'POSTACCIDENT_TEST' AND effectiveto IS NULL;
