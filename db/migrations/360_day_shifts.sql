-- ################################################################################################
-- # 360 - the day's shifts: which vehicle each working driver takes, and over what hours.
-- #
-- # The weekly hours on a driver's record (drivershifts) say when they usually work. A day's
-- # shift is the plan for one date: this driver, in this vehicle, from this time to that one -
-- # generated from the day's roster or entered by hand, and only ever a pairing the compliance
-- # rules allow (app/shifts.py). One shift per driver per day; a vehicle is on one shift at a time.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS dayshifts (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    workday      DATE         NOT NULL,
    driverid     VARCHAR(36)  NOT NULL,
    vehicleid    VARCHAR(36)  NOT NULL,
    startsat     TIME         NOT NULL,
    -- An end before the start runs past midnight, as on drivershifts.
    endsat       TIME         NOT NULL,
    source       VARCHAR(8)   NOT NULL DEFAULT 'manual',   -- auto | manual
    reasons      TEXT         NULL,                        -- why auto generation chose this vehicle
    added        DATETIME     NOT NULL,
    addedby      VARCHAR(36)  NULL,
    updated      DATETIME     NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_dayshifts_driver (accountid, workday, driverid),
    KEY ix_dayshifts_vehicle (accountid, workday, vehicleid),
    CONSTRAINT ck_dayshifts_source CHECK (source IN ('auto', 'manual'))
);
