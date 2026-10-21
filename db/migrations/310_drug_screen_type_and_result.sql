-- ################################################################################################
-- # 310 - a drug screen records what was screened for and what came back.
-- #
-- # The company's own screen was filed as a date and a document, so its table could say neither
-- # which panel was run nor whether it came back negative. Both are on the record now.
-- ################################################################################################

ALTER TABLE credentials
  ADD COLUMN IF NOT EXISTS screentype VARCHAR(32) NULL AFTER testedby,
  ADD COLUMN IF NOT EXISTS result VARCHAR(16) NULL AFTER screentype;
