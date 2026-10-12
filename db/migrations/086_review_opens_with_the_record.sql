-- ################################################################################################
-- # 086 - the annual review is opened by the record arriving, not by somebody finishing it.
-- #
-- # A driving record that comes back is work owed: 49 CFR 391.25 asks the carrier to consider it
-- # and to note what it made of it. Until this migration a review existed only once it was
-- # complete, so the work owed lived nowhere and had to be inferred from records with nothing
-- # attached to them.
-- #
-- # Now a review is opened the moment a record is received - one per record, carrying the licence
-- # and the record it belongs to - and is completed later, by signature here or by a copy of one
-- # done elsewhere. An open review is one with no finding on it; that is the whole of the
-- # distinction, so nothing can be complete without saying what it found.
-- ################################################################################################
ALTER TABLE annualreviews
    MODIFY COLUMN reviewedon DATE         NULL,
    MODIFY COLUMN finding    VARCHAR(16)  NULL,
    MODIFY COLUMN reviewer   VARCHAR(128) NULL;

-- Every record already on file that has no review against it gets the one it was always owed.
INSERT INTO annualreviews (recordid, accountid, driverid, licenseid, mvrid, mvron, method, createdon)
SELECT UUID(), m.accountid, m.driverid, m.licenseid, m.recordid, m.issuedon, 'form', m.receivedon
  FROM drivermvrs m
  LEFT JOIN annualreviews r ON r.mvrid = m.recordid
 WHERE m.receivedon IS NOT NULL AND r.recordid IS NULL;
