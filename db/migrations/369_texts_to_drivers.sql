-- ################################################################################################
-- # 369 - every text message sent to a driver, kept.
-- #
-- # A driver is texted when a trip is given to them, changed, taken off them or canceled
-- # (app/sms.py). The text names the trip and the time and nothing about the passenger; the details
-- # are in the app. Kept so "were they told?" has an answer: when, what, and what Twilio said.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS drivertexts (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    driverid     VARCHAR(36)  NOT NULL,
    tripid       VARCHAR(36)  NULL,
    legid        VARCHAR(36)  NULL,
    kind         VARCHAR(16)  NOT NULL,              -- assigned | changed | removed | canceled
    tonumber     VARCHAR(20)  NULL,
    body         VARCHAR(480) NOT NULL,
    -- queued, then sent or failed; off (texting not set up) and nophone (no number on file) are
    -- never sent.
    status       VARCHAR(12)  NOT NULL DEFAULT 'queued',
    twiliosid    VARCHAR(64)  NULL,
    error        VARCHAR(400) NULL,
    added        DATETIME     NOT NULL,
    sent         DATETIME     NULL,
    PRIMARY KEY (recordid),
    KEY ix_drivertexts_driver (accountid, driverid, added),
    KEY ix_drivertexts_trip (accountid, tripid)
);
