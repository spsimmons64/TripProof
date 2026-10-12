-- ################################################################################################
-- # 112 - a tick box is off until somebody ticks it.
-- #
-- # The four driver flags were nullable with no default, so a driver could hold NULL - a third
-- # state the control cannot show and nobody can set. 111 already taught the engine to read NULL as
-- # off, which was the right reading; this makes the column say the same thing, so the reading is
-- # not something a later change can forget.
-- #
-- # `forcompensation` on a vehicle defaulted to 1, which was a judgement dressed as a default: it
-- # assumed every vehicle added to an NEMT fleet carries passengers for hire. That assumption is
-- # usually right, and it is still not the database's to make - a box that arrives pre-ticked is an
-- # answer nobody gave.
-- #
-- # WORTH KNOWING WHAT THIS CHANGES. `forcompensation` is one prong of 49 CFR 390.5(2): more than 8
-- # passengers including the driver, FOR COMPENSATION. A new 12-seat van added with the box left
-- # unticked is not a federal commercial motor vehicle, and Part 391 will not reach whoever drives
-- # it. Existing vehicles are untouched - only the default for new ones moves - but the box now has
-- # to be ticked deliberately, and the vehicle page shows the conclusion with its reasoning so a
-- # van reading "not a commercial motor vehicle" can be argued with on sight.
-- ################################################################################################

UPDATE drivers SET operatescmv   = 0 WHERE operatescmv   IS NULL;
UPDATE drivers SET operatescdl   = 0 WHERE operatescdl   IS NULL;
UPDATE drivers SET operatesheavy = 0 WHERE operatesheavy IS NULL;
UPDATE drivers SET chapter1490   = 0 WHERE chapter1490   IS NULL;

ALTER TABLE drivers
    MODIFY COLUMN operatescmv   TINYINT(1) NOT NULL DEFAULT 0,
    MODIFY COLUMN operatescdl   TINYINT(1) NOT NULL DEFAULT 0,
    MODIFY COLUMN operatesheavy TINYINT(1) NOT NULL DEFAULT 0,
    MODIFY COLUMN chapter1490   TINYINT(1) NOT NULL DEFAULT 0;

ALTER TABLE vehicles
    MODIFY COLUMN forcompensation TINYINT(1) NOT NULL DEFAULT 0;
