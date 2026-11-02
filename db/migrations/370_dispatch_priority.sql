-- ################################################################################################
-- # 370 - which trips Auto Assign places first when there are not drivers enough for all of them.
-- #
-- # A trip can be critical - dialysis, chemotherapy, anything a passenger cannot miss - and a
-- # place can be one every trip to it is critical for, which ticks the trip when it is booked.
-- # Then the company's own ranking of who pays: High, Normal or Low for each payer, private pay
-- # included, kept beside the fee schedule it chose for that payer.
-- ################################################################################################

ALTER TABLE trips ADD COLUMN IF NOT EXISTS critical TINYINT(1) NOT NULL DEFAULT 0 AFTER servicelevel;
ALTER TABLE places ADD COLUMN IF NOT EXISTS critical TINYINT(1) NOT NULL DEFAULT 0 AFTER phone;
ALTER TABLE accountpayers ADD COLUMN IF NOT EXISTS priority VARCHAR(8) NOT NULL DEFAULT 'normal' AFTER scheduleid;
