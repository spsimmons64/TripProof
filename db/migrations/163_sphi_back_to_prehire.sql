-- ################################################################################################
-- # 163 - the safety performance history goes back in front of the hiring decision.
-- #
-- # Migration 145 moved it to `athire` on the reasoning that 49 CFR 391.23(d) gives the carrier 30
-- # days from the start of employment to complete it, so it is not a thing that must be finished
-- # before somebody is taken on.
-- #
-- # That reasoning is right about the deadline and wrong about the screen. The whole point of
-- # asking previous employers is to find out whether this person had accidents or drug and alcohol
-- # violations somewhere else - which is exactly the kind of thing a hiring decision turns on. A
-- # person deciding whether to take somebody on needs to see that the inquiries have gone out and
-- # what came back, even though the clock does not run out for another month.
-- #
-- # The 30 days are not lost: the rule carries them in its own note, which the screen prints under
-- # the citation.
-- ################################################################################################

UPDATE compliancerules
   SET duestage = 'prehire'
 WHERE subject = 'driver' AND code = 'SAFETY_PERFORMANCE_HISTORY' AND effectiveto IS NULL;
