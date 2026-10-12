-- ################################################################################################
-- # 075 - whether the company will put this driver in a commercial vehicle.
-- #
-- # Until now that was read from the licence they hold, which answers a different question: a Class
-- # B holder can drive a commercial vehicle, but whether this company will put them in one is the
-- # company's decision, not the card's. Where the company has said, its answer governs; where it has
-- # not, the licence stands in as before.
-- ################################################################################################
ALTER TABLE drivers ADD COLUMN operatescmv TINYINT(1) NULL AFTER endorsements;
