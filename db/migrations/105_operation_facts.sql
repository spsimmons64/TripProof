-- ################################################################################################
-- # 105 - the facts the engine has to have before it can decide anything.
-- #
-- # Four facts, and without them nothing in the matrix can be computed rather than guessed.
-- #
-- # THE VEHICLE. Whether a vehicle is a commercial motor vehicle is a conclusion, not a tick box,
-- # and the two definitions that matter do not agree:
-- #
-- #   49 CFR 390.5      10,001 lb GVWR *or GCWR*; or more than 8 passengers including the driver
-- #                     FOR COMPENSATION; or more than 15 not for compensation
-- #   F.S. 316.003(14)  10,000 lb GVWR; or more than 15 passengers including the driver, whether
-- #                     or not for compensation - Florida has no compensation prong at all
-- #
-- # `seats` and `gvwr` are already recorded (069). The two that were missing are the ones that
-- # decide the federal answer for a typical NEMT van: the combination weight rating, and whether
-- # passengers are carried for compensation. A twelve-seat van for hire is a federal CMV and is not
-- # a Florida one, and neither of those sentences could be evaluated before this migration.
-- #
-- # `forcompensation` defaults to 1 because that is what an NEMT operation is; a volunteer or
-- # employee-shuttle vehicle is the exception and is unticked on the vehicle.
-- #
-- # THE COMMERCE. Whether the driving is interstate decides whether the federal rules reach the
-- # operation at all (49 CFR 390.3T(a)(1)). Florida re-applies a frozen copy of them to intrastate
-- # operation on its own terms (F.S. 316.302), and then exempts most NEMT vehicles from it. So the
-- # same van owes a driver qualification file on an interstate run and a drug testing programme on
-- # an intrastate one. Nothing could ask that question before now.
-- #
-- # It is NULL, not 0, until somebody answers it: "we have not said" and "no" are different, and
-- # only one of them is safe to compute from. The account carries the ordinary answer and a trip
-- # may contradict it, because a company that runs locally six days a week and crosses a state line
-- # on the seventh is one company with two answers.
-- ################################################################################################

ALTER TABLE vehicles
    ADD COLUMN IF NOT EXISTS gcwr            INT        NULL AFTER gvwr,
    ADD COLUMN IF NOT EXISTS forcompensation TINYINT(1) NOT NULL DEFAULT 1 AFTER gcwr;

-- How this company ordinarily operates. NULL = not answered yet.
ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS interstate TINYINT(1) NULL;

-- One trip that differs from the company's ordinary answer. NULL = whatever the account says.
ALTER TABLE trips
    ADD COLUMN IF NOT EXISTS interstate TINYINT(1) NULL;
