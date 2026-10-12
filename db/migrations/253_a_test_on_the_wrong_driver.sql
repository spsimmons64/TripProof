-- Taking back a drug or alcohol test that was filed on the wrong driver.
--
-- There was no way to. A test typed against the wrong name stayed there, and what it CAUSED
-- stayed with it: a positive puts a bar on safety-sensitive work, a negative return-to-duty test
-- lifts one, a random test answers a selection, a post-accident test closes out 382.303. Fixing
-- the mistake means undoing all of that, which nobody can do by hand without leaving a driver
-- either barred for something that never happened to them or cleared by a test that was not
-- theirs.
--
-- WITHDRAWN, NOT DELETED
--
-- 49 CFR 382.401 asks the employer to keep these records, and in any case a positive result that
-- simply disappears out of a file is the worst thing an auditor can find. A withdrawn row with a
-- date, a person and a reason against it is a correction anybody can follow. A missing row is
-- indistinguishable from a cover-up.
--
-- The same three columns go on the prohibition, because a bar raised by a test that was never
-- this driver's has to come down the same way - visibly, with its reason, rather than vanishing.

-- IF NOT EXISTS throughout: DDL commits implicitly in MariaDB, so a migration that fails
-- halfway has already written part of itself, and the next start re-runs it from the top.

ALTER TABLE drugtests
  ADD COLUMN IF NOT EXISTS withdrawn       datetime     DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS withdrawnby     varchar(36)  DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS withdrawnreason varchar(255) DEFAULT NULL;

ALTER TABLE driverprohibitions
  ADD COLUMN IF NOT EXISTS withdrawn       datetime     DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS withdrawnby     varchar(36)  DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS withdrawnreason varchar(255) DEFAULT NULL;

CREATE INDEX IF NOT EXISTS ix_drugtests_live ON drugtests (accountid, driverid, withdrawn);
