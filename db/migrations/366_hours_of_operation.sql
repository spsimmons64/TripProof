-- ################################################################################################
-- # 366 - when the company is open, day by day.
-- #
-- # JSON keyed by weekday, Monday 0 to Sunday 6: {"open": "08:00", "close": "17:00"}, or null for a
-- # day it is closed. Entered on the Company page; Dispatch draws its day from it.
-- ################################################################################################

ALTER TABLE accounts ADD COLUMN IF NOT EXISTS hours TEXT NULL;
