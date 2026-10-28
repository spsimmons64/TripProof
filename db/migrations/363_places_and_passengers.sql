-- ################################################################################################
-- # 363 - the places a company drives to, and the passengers it drives, kept to be chosen from.
-- #
-- # Book A Trip picks the drop-off from the company's places (BAYFRONT HOSPITAL, its address and
-- # telephone) and the passenger from its passengers (name, home address, telephone) rather than
-- # having them typed again every time. One not on the list is added from the same screen.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS places (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    name         VARCHAR(160) NOT NULL,
    address      VARCHAR(255) NOT NULL,
    phone        VARCHAR(32)  NULL,
    added        DATETIME     NOT NULL,
    addedby      VARCHAR(36)  NULL,
    deleted      DATETIME     NULL,
    PRIMARY KEY (recordid),
    KEY ix_places_account (accountid, name)
);

CREATE TABLE IF NOT EXISTS passengers (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    name         VARCHAR(160) NOT NULL,
    address      VARCHAR(255) NOT NULL,
    phone        VARCHAR(32)  NULL,
    added        DATETIME     NOT NULL,
    addedby      VARCHAR(36)  NULL,
    deleted      DATETIME     NULL,
    PRIMARY KEY (recordid),
    KEY ix_passengers_account (accountid, name)
);
