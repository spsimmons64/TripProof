-- ################################################################################################
-- # 374 - the will-call line: one number for every passenger to ring when they are ready.
-- #
-- # The company's Twilio number. In Transportation Hours a call to it is put through to the office;
-- # after closing, to whoever is on call at that moment; with nobody on call, the caller is told
-- # somebody will ring back, and the call waits on Dispatch in the morning. Every call is kept.
-- #
-- # The on-call driver is also texted when on call begins and as each will-call comes due. Each of
-- # those is written down once, so a restart never sends one twice.
-- ################################################################################################

ALTER TABLE accounts ADD COLUMN IF NOT EXISTS willcallnumber VARCHAR(32) NULL;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS officephone VARCHAR(32) NULL;

CREATE TABLE IF NOT EXISTS linecalls (
    recordid      VARCHAR(36)  NOT NULL,
    accountid     VARCHAR(36)  NOT NULL,
    callsid       VARCHAR(64)  NOT NULL,
    fromnumber    VARCHAR(32)  NULL,
    passenger     VARCHAR(160) NULL,                -- who it is, where the number is one we know
    receivedon    DATETIME     NOT NULL,            -- UTC
    routed        VARCHAR(8)   NOT NULL,            -- office | oncall | nobody
    driverid      VARCHAR(36)  NULL,                -- the on-call driver it was put through to
    outcome       VARCHAR(16)  NULL,                -- answered | missed, once the call has ended
    dealtwithon   DATETIME     NULL,
    dealtwithby   VARCHAR(36)  NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_linecalls_sid (callsid),
    KEY ix_linecalls_account (accountid, receivedon)
);

CREATE TABLE IF NOT EXISTS oncalltexts (
    dedupe        VARCHAR(160) NOT NULL,            -- what this text was for, once: start / due
    accountid     VARCHAR(36)  NOT NULL,
    driverid      VARCHAR(36)  NOT NULL,
    legid         VARCHAR(36)  NULL,
    senton        DATETIME     NOT NULL,
    PRIMARY KEY (dedupe)
);
