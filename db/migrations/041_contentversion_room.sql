-- ################################################################################################
-- # 041 - a signature against a company policy names the credential it was filed under, so the
-- # version it records is "company:<recordid>" rather than a short date-stamped version of ours.
-- # Sixteen characters was room enough for "2026-09-23b"; it is not room enough for that.
-- ################################################################################################
ALTER TABLE documentsignatures MODIFY COLUMN contentversion VARCHAR(64) NULL;
