-- ################################################################################################
-- # 384 - no work days.
-- #
-- # Who drives is decided the morning of, when Auto Assign asks "Who's driving today?" - easier than
-- # keeping a schedule true. Weeks ahead every hired driver counts, less anybody marked out.
-- ################################################################################################

ALTER TABLE drivers DROP COLUMN IF EXISTS workdays;
