-- ################################################################################################
-- # 368 - drivers' weekly working hours retired.
-- #
-- # Who works when is now the day's vehicle assignments (dayshifts, 360), drawn within the
-- # company's hours of operation (366). The weekly pattern on a driver's record no longer has a
-- # screen, and nothing reads it: kept, it would be a rule nobody can see or change.
-- ################################################################################################

DROP TABLE IF EXISTS drivershifts;
