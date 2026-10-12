-- ################################################################################################
-- # 151 - the SAP list itself, not just the day it was handed over.
-- #
-- # 49 CFR 40.287 requires the employer to give an applicant who fails or refuses a test a list of
-- # DOT-qualified substance abuse professionals. Migration 150 recorded the date that was done,
-- # which is the same mistake migration 135 fixed for the return-to-duty paperwork: a date with
-- # nothing behind it is somebody's word for it.
-- #
-- # This is the list that was given. It is kept apart from `documentid`, which is the SAP's own
-- # written determination at the far end of the process - the two are different documents written
-- # by different people about different things, and sharing a column would lose one of them.
-- ################################################################################################

ALTER TABLE driverprohibitions
    ADD COLUMN IF NOT EXISTS sapinfodocumentid VARCHAR(36) NULL AFTER sapinfogivenby;
