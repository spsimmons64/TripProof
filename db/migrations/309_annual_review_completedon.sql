-- ################################################################################################
-- # 309 - when an annual review was completed, to the second.
-- #
-- # A driving record received after a review was completed has been reviewed by nobody, and the
-- # review stops answering until another is completed. The review date alone cannot tell a record
-- # that came in that afternoon from one read that morning.
-- ################################################################################################

ALTER TABLE annualreviews ADD COLUMN IF NOT EXISTS completedon DATETIME NULL AFTER reviewedon;
