-- ################################################################################################
-- # 382 - planned runs: a vehicle and its hours, with the driver still to be named.
-- #
-- # A vehicle assignment may be made before anybody is put in it ("MT-LIFT1, 7 to 5, driver to be
-- # named"): capacity, so trips can be booked against the day before its drivers are known. A trip
-- # that only fits on such a run is booked At Risk, and said to be.
-- #
-- # And each weekday's usual runs - the vehicles and hours a company ordinarily runs that day - so a
-- # day nobody has planned yet is still read as having them, At Risk, until it is planned.
-- ################################################################################################

ALTER TABLE dayshifts MODIFY driverid VARCHAR(36) NULL;

CREATE TABLE IF NOT EXISTS usualruns (
    recordid      VARCHAR(36)  NOT NULL,
    accountid     VARCHAR(36)  NOT NULL,
    weekday       TINYINT      NOT NULL,            -- 0 Monday to 6 Sunday
    vehicleid     VARCHAR(36)  NOT NULL,
    startsat      TIME         NOT NULL,
    endsat        TIME         NOT NULL,
    added         DATETIME     NOT NULL,
    addedby       VARCHAR(36)  NOT NULL,
    PRIMARY KEY (recordid),
    KEY ix_usualruns_day (accountid, weekday)
);
