-- ################################################################################################
-- # 085 - driver, licence, driving record, annual review: one chain.
-- #
-- # A driving record on file is not the end of anything. Somebody has to read it - for violations,
-- # suspensions, revocations, accidents, anything disqualifying - and that reading is what the
-- # annual review of 49 CFR 391.25 records. So a record moves through states rather than simply
-- # existing: sent for, on file and unread, read, and then reviewed with a finding.
-- #
-- # The annual review is fixed to the record it was made on, and the record to the licence it was
-- # pulled on. That is what lets the file answer "which driving record did this review look at?",
-- # which is the question an auditor asks and the one a date alone cannot answer.
-- ################################################################################################
ALTER TABLE drivermvrs
    ADD COLUMN reviewstate VARCHAR(12) NOT NULL DEFAULT 'pending' AFTER documentid,
    ADD COLUMN reviewedon  DATETIME    NULL AFTER reviewstate,
    ADD COLUMN reviewedby  VARCHAR(36) NULL AFTER reviewedon,
    ADD CONSTRAINT ck_drivermvrs_reviewstate CHECK (reviewstate IN ('pending', 'reviewed'));

-- An order has nothing to read yet; only a record on file waits on a reader.
UPDATE drivermvrs SET reviewstate = 'pending' WHERE receivedon IS NOT NULL;

ALTER TABLE annualreviews
    ADD COLUMN licenseid VARCHAR(36) NULL AFTER driverid,
    -- How the review was made: signed here, or done elsewhere and filed. Either way it carries a
    -- finding, because a scan of somebody else's form is not a result this system can read.
    ADD COLUMN method    VARCHAR(10)  NOT NULL DEFAULT 'form' AFTER finding,
    ADD CONSTRAINT ck_annualreviews_method CHECK (method IN ('form', 'upload'));
