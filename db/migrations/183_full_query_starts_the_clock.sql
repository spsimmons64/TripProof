-- ################################################################################################
-- # 183 - the pre-employment full query is a query.
-- #
-- # 382.701(a) asks for a full query before the driver performs safety-sensitive functions.
-- # 382.701(b) asks for a query at least once every twelve months. They are two paragraphs of the
-- # same section and the second counts from the last query, so a full query run at hire satisfies
-- # the annual obligation for that year - the next one falls due twelve months later.
-- #
-- # The annual rule looked only at its own credential and therefore read "nothing on file yet"
-- # beside a full query filed the same week, which is the engine telling somebody to do again what
-- # they have just done. `alternatesource` is the mechanism for exactly this: two requirements, one
-- # record, and no condition on it because there is none - a full query is always a query.
-- #
-- # 391.25 is deliberately NOT given the same treatment. The annual inquiry and review is a second
-- # act: a NEW record obtained within twelve months and a reviewer's signed note on it. The
-- # pre-employment MVR does not answer it, and saying it did would put a green tick where there is
-- # no review. What that rule needed instead was a date - see rules.deadline().
-- ################################################################################################

UPDATE compliancerules
   SET alternatesource = 'report:CLEARINGHOUSE_PREEMP'
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'CLEARINGHOUSE';
