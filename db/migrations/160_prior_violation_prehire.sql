-- ################################################################################################
-- # 160 - the prior-violation verification belongs to the hiring decision.
-- #
-- # It was `predrive`, alongside the medical card and the road test, on the reasoning that those
-- # decide whether somebody already taken on may now drive. This one is different: 49 CFR 40.25(j)
-- # asks the question during hiring, and the answer is one of the few things that genuinely bears
-- # on whether to take the person on at all - a disclosed violation with no documented return to
-- # duty means they cannot be used for safety-sensitive work the day they start.
-- #
-- # Somebody making a hiring decision needs to see it while they are making it, not afterwards.
-- ################################################################################################

UPDATE compliancerules
   SET duestage = 'prehire'
 WHERE subject = 'driver' AND code = 'PRIOR_VIOLATION_RTD' AND effectiveto IS NULL;
