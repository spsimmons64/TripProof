-- ################################################################################################
-- # 398 - "the newest check of this leg" decides whether Dispatch flags it. Two checks in the same
-- # second (a driver disqualified and cleared, a record filed and read) could not be told apart, so
-- # the moment a check was made is kept to the microsecond.
-- ################################################################################################

ALTER TABLE tripeligibility MODIFY evaluatedon DATETIME(6) NOT NULL;
