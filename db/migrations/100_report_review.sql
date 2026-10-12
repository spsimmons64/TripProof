-- ################################################################################################
-- # 100 - a report on file has either been read or it has not.
-- #
-- # What the office needs to know about a PSP report, a CDLIS check or a Clearinghouse query is not
-- # a verdict somebody typed into a box when they filed it - it is whether anybody has actually
-- # read the thing. A driving record already works this way; the rest now do too.
-- #
-- # A report the office uploads has been read by definition: somebody had it in their hands to
-- # upload it. One that arrives on its own - from a provider, later - starts unread and waits for
-- # a person, which is the whole reason the distinction exists.
-- ################################################################################################
ALTER TABLE driverreports
    ADD COLUMN reviewstate VARCHAR(12) NOT NULL DEFAULT 'pending' AFTER outcome,
    ADD COLUMN reviewedon  DATETIME    NULL AFTER reviewstate,
    ADD COLUMN reviewedby  VARCHAR(36) NULL AFTER reviewedon,
    ADD CONSTRAINT ck_driverreports_reviewstate CHECK (reviewstate IN ('pending', 'reviewed'));

-- Everything already on file was put there by somebody in the office, who had it open to file it.
UPDATE driverreports SET reviewstate = 'reviewed', reviewedon = receivedon, reviewedby = receivedby
 WHERE receivedon IS NOT NULL;
