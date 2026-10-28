-- ################################################################################################
-- # 364 - a passenger's date of birth, so the office can be sure who is on the telephone.
-- #
-- # Two passengers can share a name; asked their date of birth, a caller says which one they are.
-- # Required for every passenger added from now on (routers/places.py); NULL only for any added
-- # before it was asked.
-- ################################################################################################

ALTER TABLE passengers ADD COLUMN IF NOT EXISTS dob DATE NULL AFTER name;
