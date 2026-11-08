-- ################################################################################################
-- # 407 - every vehicle in an NEMT fleet carries passengers for compensation.
-- #
-- # The vehicle form asked it with a tick box. Nothing goes in the fleet that does not carry paying
-- # passengers, so it is always yes, and the 9-to-15 passenger prong of 49 CFR 390.5 reads it so.
-- ################################################################################################

UPDATE vehicles SET forcompensation = 1 WHERE forcompensation = 0 OR forcompensation IS NULL;
ALTER TABLE vehicles ALTER COLUMN forcompensation SET DEFAULT 1;
