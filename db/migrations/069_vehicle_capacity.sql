-- ################################################################################################
-- # 069 - what the vehicle is, so the licence it needs is a fact rather than an assumption.
-- #
-- # Which licence a driver needs follows the vehicle, not the programme the company runs under. A
-- # twelve-seat van in a Chapter 14-90 transit operation is still a twelve-seat van: the driver may
-- # hold an ordinary Florida Class E. A sixteen-seat bus is a passenger commercial vehicle whoever
-- # is paying for the trip, and its driver needs a commercial licence with a passenger endorsement.
-- #
-- #   seats   designed occupancy INCLUDING the driver, which is how both Florida and the federal
-- #           rules count it: more than 15 is the line
-- #   gvwr    gross vehicle weight rating in pounds; 26,001 and above is the other line
-- #
-- # Chapter 14-90's own requirements - the medical examination, the training records, the duty
-- # status record, the licence suspension reporting - are separate, and stay that way.
-- ################################################################################################
ALTER TABLE vehicles
    ADD COLUMN seats SMALLINT NULL AFTER modelyear,
    ADD COLUMN lift  TINYINT(1) NOT NULL DEFAULT 0 AFTER seats;
