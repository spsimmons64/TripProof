-- ################################################################################################
-- # 175 - when a requirement is due, in its own words where the stage is not the whole truth.
-- #
-- # The stage says which decision a requirement belongs to - before hiring, once hired, ongoing -
-- # and for most of them that is all anybody needs. The safety performance history is different:
-- # it belongs in front of the hiring decision, because what a previous employer says about
-- # accidents and drug violations is exactly what that decision turns on, but 49 CFR 391.23(d)
-- # gives the carrier 30 days FROM THE START OF EMPLOYMENT to finish it. "Before hiring" is
-- # therefore the right place and the wrong sentence.
-- #
-- # So a rule may carry the sentence it wants printed, and the stage goes on deciding which section
-- # it lives in. Two different jobs that were being done by one word.
-- ################################################################################################

ALTER TABLE compliancerules
    ADD COLUMN IF NOT EXISTS duetext VARCHAR(80) NULL AFTER duestage;

UPDATE compliancerules
   SET duetext = 'Complete no later than 30 days after hire date'
 WHERE subject = 'driver' AND code = 'SAFETY_PERFORMANCE_HISTORY' AND effectiveto IS NULL;
