-- ################################################################################################
-- # 153 - a report's outcome is not always a grade.
-- #
-- # Migration 087 pinned `driverreports.outcome` to clear | review | flagged, which are the words
-- # for a reader's judgement about a report: somebody read the crash history and formed a view.
-- #
-- # A Clearinghouse query is not that. It answers one question with teeth on it - whether this
-- # driver may perform safety-sensitive functions (49 CFR 382.701(a)) - and the office records that
-- # determination in the question's own words. "Clear" would be a translation, and a translation of
-- # a regulatory finding is a worse record than the finding.
-- #
-- # The constraint stays, widened, because it is doing its job: it is what stopped these words
-- # being written before anybody had thought about where they belong.
-- ################################################################################################

ALTER TABLE driverreports DROP CONSTRAINT IF EXISTS ck_driverreports_outcome;

ALTER TABLE driverreports
    ADD CONSTRAINT ck_driverreports_outcome CHECK (
        outcome IS NULL OR outcome IN ('clear', 'review', 'flagged', 'qualified', 'prohibited'));
