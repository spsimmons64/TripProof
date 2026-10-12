-- ################################################################################################
-- # 164 - the 30-day note comes off the safety performance history.
-- #
-- # It was there to explain why the requirement sat after hiring. It sits before hiring now
-- # (migration 163), so the sentence is answering a question nobody is asking, and the warning
-- # colours it wears say "read this" about something that needs no reading.
-- ################################################################################################

UPDATE compliancerules
   SET note = NULL
 WHERE subject = 'driver' AND code = 'SAFETY_PERFORMANCE_HISTORY' AND effectiveto IS NULL;
