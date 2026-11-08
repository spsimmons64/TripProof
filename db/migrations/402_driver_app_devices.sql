-- ################################################################################################
-- # 402 - the store app. A phone with TripProofDriver installed registers itself, and the driver is
-- # told about their trips by a notification on it instead of a text. A driver without the app, or
-- # whose phone the notification service has forgotten, is still texted.
-- #
-- # And a driver can delete their own app login from inside the app, which both stores require.
-- ################################################################################################

-- One row per phone a driver has signed in on. Signing in on another phone ends the previous one
-- (one device at a time, as the session already is), and a token the notification service says
-- it no longer knows is ended where it is found.
CREATE TABLE IF NOT EXISTS driverdevices (
    recordid   VARCHAR(36)  NOT NULL,
    accountid  VARCHAR(36)  NOT NULL,
    driverid   VARCHAR(36)  NOT NULL,
    platform   VARCHAR(10)  NOT NULL,              -- android | ios
    token      VARCHAR(400) NOT NULL,              -- the Firebase Cloud Messaging registration token
    added      DATETIME     NOT NULL,
    lastseen   DATETIME     NOT NULL,
    ended      DATETIME     NULL,
    PRIMARY KEY (recordid),
    KEY ix_driverdevices_driver (accountid, driverid, ended),
    KEY ix_driverdevices_token (token(191))
);

-- How each message to a driver went: sms, or push to the app.
ALTER TABLE drivertexts ADD COLUMN IF NOT EXISTS channel VARCHAR(8) NOT NULL DEFAULT 'sms' AFTER kind;

-- A driver who deleted their app login from the app. The login goes at once; what the company is
-- required to keep about the driver is the company's record and stays.
CREATE TABLE IF NOT EXISTS driverdeletions (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    driverid     VARCHAR(36)  NOT NULL,
    requestedon  DATETIME     NOT NULL,
    ip           VARCHAR(64)  NULL,
    PRIMARY KEY (recordid),
    KEY ix_driverdeletions_driver (accountid, driverid)
);
