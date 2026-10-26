-- ################################################################################################
-- # 359 - a driver's answers that did not come through an online application.
-- #
-- # Two requirements turn on what the driver says: the 40.25(j) pre-employment questionnaire and
-- # whether a license has been revoked, suspended or denied (FL_LICENSE_STATUS_NOTICE). Both were
-- # read only off the online application, so a driver the office entered could never answer them -
-- # the questionnaire link failed with "no application to record the answer on", and the license
-- # question had nothing that asked it at all (MODIVTEST B-04). The driver answers either by link,
-- # signed, and where there is no application the answer is kept here, in the same shape as the
-- # application's own step - one step per row - so the engine reads both the same way.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS driveranswers (
    accountid    VARCHAR(36)  NOT NULL,
    driverid     VARCHAR(36)  NOT NULL,
    step         VARCHAR(8)   NOT NULL,
    data         TEXT         NOT NULL CHECK (JSON_VALID(data)),
    answeredon   DATETIME     NOT NULL,
    requestid    VARCHAR(36)  NULL,       -- the uploadrequests row it came back on
    PRIMARY KEY (driverid, step),
    KEY ix_driveranswers_account (accountid)
);

-- The request has to name something, as the questionnaire's does (migration 148). Nothing is filed
-- against it; inactive so it is not offered as a document to file.
INSERT INTO credentialtypes (recordid, code, name, subject, active)
SELECT UUID(), 'LICENSE_ACTION_QUESTION',
       'License revocation, suspension or denial question', 'driver', 0
 WHERE NOT EXISTS (SELECT 1 FROM credentialtypes WHERE code = 'LICENSE_ACTION_QUESTION');
