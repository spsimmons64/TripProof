-- ################################################################################################
-- # 355 - every edit to a booked trip, kept: what changed, from what to what, who changed it, why,
-- # and - where a driver was already on the leg - when the driver saw it.
-- #
-- # One row per edit per leg it touched (legid NULL for an edit that touched no leg). `changes` is
-- # the list of fields, each with its label and its old and new value as shown, so the record reads
-- # the same in a year as it does today whatever the screens are called by then. `driverid` is the
-- # driver who has to be told; `seenon` is when they said they had read it. A leg with a change its
-- # driver has not seen will not move to its next step.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS tripchanges (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    tripid       VARCHAR(36)  NOT NULL,
    legid        VARCHAR(36)  NULL,
    changedon    DATETIME     NOT NULL,
    changedby    VARCHAR(36)  NOT NULL,
    reason       TEXT         NULL,
    changes      TEXT         NOT NULL,
    driverid     VARCHAR(36)  NULL,
    legstate     VARCHAR(16)  NULL,       -- where the leg was when it was changed
    seenon       DATETIME     NULL,
    PRIMARY KEY (recordid),
    KEY ix_tripchanges_trip (accountid, tripid, changedon),
    KEY ix_tripchanges_unseen (accountid, legid, driverid, seenon)
);
