-- ################################################################################################
-- # 386 - Trip Review: a finished trip is read before anybody bills it.
-- #
-- # Who looked and when, and why one was held. verifystate already carries where it stands:
-- # awaitingreview, verified, or needscorrection (on hold).
-- ################################################################################################

ALTER TABLE trips ADD COLUMN IF NOT EXISTS reviewedon DATETIME NULL AFTER verifystate;
ALTER TABLE trips ADD COLUMN IF NOT EXISTS reviewedby VARCHAR(36) NULL AFTER reviewedon;
ALTER TABLE trips ADD COLUMN IF NOT EXISTS holdreason VARCHAR(600) NULL AFTER reviewedby;
