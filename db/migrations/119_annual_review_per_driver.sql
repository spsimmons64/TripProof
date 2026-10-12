-- ################################################################################################
-- # 119 - the annual review belongs to the driver, not to a driving record.
-- #
-- # It was built the wrong way round: `annualreviews` carried a `mvrid` and a `licenseid`, so every
-- # record that arrived opened a review of its own. A driver holding licences in three states got
-- # three annual reviews in a year, which is not what 49 CFR 391.25 asks for and is not a thing an
-- # auditor would recognise. The data already shows it - one driver here has four reviews against
-- # one Florida licence.
-- #
-- # 391.25(b) asks the carrier to "review the motor vehicle record of each driver it employs to
-- # determine whether that driver meets minimum requirements for safe driving or is disqualified".
-- # One driver, one determination, at least once every 12 months. The records are what the reviewer
-- # reads; they are evidence for the review, not occasions for it.
-- #
-- #                      ANNUAL REVIEW  (driver + period)
-- #                             |
-- #                 +-----------+-----------+
-- #                 |           |           |
-- #              FL MVR      GA MVR      AL MVR
-- #                 |           |           |
-- #                 +-----------+-----------+
-- #                             |
-- #                   Qualified / Disqualified
-- #
-- # The period is the twelve months a review speaks for. `mvrid` and `licenseid` stay on the table
-- # so the reviews already signed still read exactly as they were signed - a signed record is never
-- # rewritten - but nothing new populates them, and the records considered live in the join.
-- ################################################################################################

ALTER TABLE annualreviews
    ADD COLUMN IF NOT EXISTS periodstart DATE NULL AFTER driverid,
    ADD COLUMN IF NOT EXISTS periodend   DATE NULL AFTER periodstart;

-- Which driving records a review was performed against. A review reads every record that answers
-- the period, and one record can only be read by the review that covers it.
CREATE TABLE IF NOT EXISTS annualreviewmvrs (
    reviewid  VARCHAR(36) NOT NULL,
    mvrid     VARCHAR(36) NOT NULL,
    added     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (reviewid, mvrid),
    KEY ix_annualreviewmvrs_mvr (mvrid),
    CONSTRAINT fk_arm_review FOREIGN KEY (reviewid) REFERENCES annualreviews (recordid) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Carry the existing reviews across: whatever record each was opened from becomes the first record
-- attached to it, and its period is the twelve months it was performed at the end of.
INSERT IGNORE INTO annualreviewmvrs (reviewid, mvrid)
SELECT recordid, mvrid FROM annualreviews WHERE mvrid IS NOT NULL;

UPDATE annualreviews
   SET periodend   = COALESCE(periodend, reviewedon, DATE(createdon)),
       periodstart = COALESCE(periodstart,
                              DATE_SUB(COALESCE(reviewedon, DATE(createdon)), INTERVAL 1 YEAR))
 WHERE periodend IS NULL OR periodstart IS NULL;
