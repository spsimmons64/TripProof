-- ################################################################################################
-- # 176 - the road test sits before hiring and is due before driving.
-- #
-- # Migration 174 moved it in front of the hiring decision, which is where somebody wants it while
-- # they are deciding. What 49 CFR 391.31 actually says is that the driver may not operate the
-- # vehicle until the test is done - which is not the same sentence, and is the one worth printing.
-- #
-- # The same split migration 175 made for the safety performance history: the stage decides which
-- # section it appears in, the sentence says when it is owed.
-- ################################################################################################

UPDATE compliancerules
   SET duetext = 'Before driving'
 WHERE subject = 'driver' AND code = 'ROAD_TEST' AND effectiveto IS NULL;
