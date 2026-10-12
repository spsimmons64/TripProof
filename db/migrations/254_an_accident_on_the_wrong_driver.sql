-- Taking back an accident recorded against the wrong driver.
--
-- The same hole the drug tests had, and there was no way to remove one at all. An accident
-- written up against the wrong name does not just sit there looking wrong: 49 CFR 382.303 reads
-- it and may conclude the driver owes a post-accident test, which then shows on their file as
-- outstanding work and on the dashboard as a reason they are not clear. Meanwhile the carrier's
-- own register under 390.15(b) carries an event that never involved that person.
--
-- Withdrawn, not deleted, for the reason the tests are: 390.15(b) asks the carrier to KEEP the
-- register for three years, and an accident that vanishes out of it is the one thing an auditor
-- cannot be shown an explanation for. A withdrawn row carries its date, its person and its
-- reason, and reads as the correction it is.
--
-- Nothing else has to be unwound. Whether a test was owed is DERIVED from the accident rather
-- than stored against the driver, so the obligation goes when the accident does - which is the
-- advantage of having computed it rather than written it down.

ALTER TABLE driveraccidents
  ADD COLUMN IF NOT EXISTS withdrawn       datetime     DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS withdrawnby     varchar(36)  DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS withdrawnreason varchar(255) DEFAULT NULL;

CREATE INDEX IF NOT EXISTS ix_driveraccidents_live
  ON driveraccidents (accountid, driverid, withdrawn);

-- And the same for a duty day.
--
-- Hours of service already soft-deleted, and was already filtered everywhere, so the record was
-- never actually lost - but it went without a reason, which makes it a disappearance rather than
-- a correction. 49 CFR 395.8(k)(1) asks the carrier to keep records of duty status for six
-- months; a day that is simply gone from a driver's week, with the arithmetic quietly different
-- afterwards, is the same problem as a drug test that vanishes.
--
-- One word for one act, across all three: withdrawn, by whom, and why. The old `deleted` column
-- stays and is still filtered, so days removed before today remain removed - there is no need to
-- migrate them, and rewriting history to use the new word would be its own small lie.

ALTER TABLE driverdutydays
  ADD COLUMN IF NOT EXISTS withdrawn       datetime     DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS withdrawnby     varchar(36)  DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS withdrawnreason varchar(255) DEFAULT NULL;
