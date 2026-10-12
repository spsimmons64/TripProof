-- ################################################################################################
-- # 113 - one question with four answers, instead of three boxes that can contradict each other.
-- #
-- # 110 put three tick boxes on the driver: operates a CMV, operates a CDL vehicle, operates
-- # something 26,001 lb or over. The comment on that migration called them independent. They are
-- # not, and the boxes made three nested facts look like three separate ones:
-- #
-- #   26,001 lb or more  ->  a CDL is required   (49 CFR 383.91(a)(2), Group B)
-- #   a CDL is required  ->  it is a CMV         (383.5 is a subset of 390.5)
-- #
-- # So the three tick boxes could express states that cannot exist - CDL without CMV, heavy without
-- # CDL - and a file holding one of those would have been evaluated against a rule set that matches
-- # no vehicle on earth. What they genuinely distinguish is only the gaps BETWEEN the thresholds:
-- #
-- #   a 12-seat van at 9,500 lb for hire   CMV under 390.5(2), no CDL       -> Part 391, no Part 382
-- #   a 16-seat bus at 14,500 lb           CDL under 383.91(a)(3), not heavy -> Part 391 and 382
-- #   a 30,000 lb straight truck            heavy, so CDL                     -> and the Florida
-- #                                                                              intrastate branch
-- #
-- # One ordered question answers all of it and cannot be self-contradictory. The three facts the
-- # rules read - driver.cmv, driver.cdl, driver.heavy - are derived from it, so no rule changes.
-- ################################################################################################

ALTER TABLE drivers
    ADD COLUMN IF NOT EXISTS operation VARCHAR(12) NOT NULL DEFAULT 'noncmv' AFTER operatescmv;

-- Carry the boxes across, reading them in the only order that makes sense.
UPDATE drivers SET operation =
    CASE WHEN operatesheavy = 1 THEN 'cdlheavy'
         WHEN operatescdl   = 1 THEN 'cdl'
         WHEN operatescmv   = 1 THEN 'cmv'
         ELSE 'noncmv' END;

-- The two boxes that only ever repeated part of the answer go entirely.
ALTER TABLE drivers
    DROP COLUMN IF EXISTS operatescdl,
    DROP COLUMN IF EXISTS operatesheavy;

-- `operatescmv` stays, because the trip evaluator, the annual review sheet and the DOT eligibility
-- check all read it - but it stops being a thing anyone can set. It is computed from `operation`,
-- so the two cannot disagree and there is still only one place the answer lives.
ALTER TABLE drivers DROP COLUMN operatescmv;
ALTER TABLE drivers
    ADD COLUMN operatescmv TINYINT(1)
        AS (CASE WHEN operation = 'noncmv' THEN 0 ELSE 1 END) STORED AFTER operation;
