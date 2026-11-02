-- ################################################################################################
-- # 381 - a confirmed trip keeps its place.
-- #
-- # When a trip was confirmed: booked (its added), or a broker's offer accepted (this). Auto Assign
-- # places the first confirmed first, and a trip confirmed later never takes its driver - only a
-- # critical trip goes before it.
-- ################################################################################################

ALTER TABLE trips ADD COLUMN IF NOT EXISTS confirmedon DATETIME NULL AFTER brokerstate;
