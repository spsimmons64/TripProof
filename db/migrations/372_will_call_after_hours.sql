-- ################################################################################################
-- # 372 - a will-call return that could run past closing has a plan, not a hope.
-- #
-- # A will-call return has no pickup time, but it still has to get the passenger home. When it is
-- # booked it is given a Ready About time - an estimate, not a promise - and if that and the drive
-- # home run past the company's Transportation Hours, the booking says how the passenger gets
-- # home: an on-call driver, or the broker arranges the return. That is the return plan.
-- #
-- # The broker arranging it is the return leg handed back on its own: the outbound is ours, the
-- # ride home is the broker's - and, like a whole trip handed back, it stays ours until the
-- # broker confirms they have it. So a leg has a broker state of its own, and a hand-back can
-- # name the leg.
-- #
-- # An on-call driver is a vehicle assignment marked On Call: the only kind that may run outside
-- # Transportation Hours, and the only kind Auto Assign uses for a pickup after closing.
-- ################################################################################################

ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS readyabout DATETIME NULL AFTER appointmentat;
ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS returnplan VARCHAR(8) NULL AFTER readyabout;
ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS brokerstate VARCHAR(16) NULL AFTER returnplan;
ALTER TABLE triprejections ADD COLUMN IF NOT EXISTS legid VARCHAR(36) NULL AFTER tripid;
ALTER TABLE dayshifts ADD COLUMN IF NOT EXISTS oncall TINYINT(1) NOT NULL DEFAULT 0 AFTER endsat;
