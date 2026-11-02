-- ################################################################################################
-- # 380 - the on-call list, apart from the vehicle assignments.
-- #
-- # Who is on call is decided on Dispatch, a tick against each driver: on call from closing until
-- # the time given, or for the rest of the day with none. The vehicle they would take goes with
-- # them, as an on-call assignment's did. Those on-call assignments move here, and come off the
-- # vehicle assignments.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS oncall (
    recordid      VARCHAR(36)  NOT NULL,
    accountid     VARCHAR(36)  NOT NULL,
    workday       DATE         NOT NULL,
    driverid      VARCHAR(36)  NOT NULL,
    vehicleid     VARCHAR(36)  NOT NULL,
    untilat       TIME         NULL,                -- none: the rest of the day
    added         DATETIME     NOT NULL,
    addedby       VARCHAR(36)  NOT NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_oncall_driver (accountid, workday, driverid)
);

INSERT IGNORE INTO oncall (recordid, accountid, workday, driverid, vehicleid, untilat, added, addedby)
SELECT recordid, accountid, workday, driverid, vehicleid, endsat, added, COALESCE(addedby, '')
FROM dayshifts WHERE oncall = 1;

DELETE FROM dayshifts WHERE oncall = 1;
