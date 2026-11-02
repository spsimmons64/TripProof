-- ################################################################################################
-- # 379 - dispatch alerts: the office is texted when the board is not being watched.
-- #
-- # Call Overdue, No Driver and Coverage Needed are flags on the Dispatch screen, and a flag only
-- # works while somebody is looking. Each office user can give a mobile and choose to be texted
-- # when one of them has stood unanswered. Trip references and times only, as every text is.
-- #
-- # The texts are kept with the drivers' (drivertexts), against the user instead of a driver.
-- ################################################################################################

ALTER TABLE users ADD COLUMN IF NOT EXISTS mobile VARCHAR(20) NULL AFTER name;
ALTER TABLE users ADD COLUMN IF NOT EXISTS dispatchalerts TINYINT(1) NOT NULL DEFAULT 0 AFTER mobile;

ALTER TABLE drivertexts MODIFY driverid VARCHAR(36) NULL;
ALTER TABLE drivertexts ADD COLUMN IF NOT EXISTS userid VARCHAR(36) NULL AFTER driverid;
