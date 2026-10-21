-- ################################################################################################
-- # 335 - imported trips are judged by the same trip check as an assignment.
-- #
-- # The evaluator read its own set of 15 requirements, seven of them asking for document types
-- # retired when licenses, driving records and screenings got tables of their own - so every
-- # imported trip would have read "at risk" however complete the driver's file. Each leg is now put
-- # to tripcheck.check, the check an assignment already goes through, and its result saved here: one
-- # row per thing that stops the leg, or one row saying it is clear.
-- #
-- # A row names the rule that judged it as it stood then - code, name, version, and whether a
-- # reviewer had approved it - so a trip judged last month is explained by last month's rule. The
-- # old requirement link stays on the rows written before this, and is no longer required.
-- ################################################################################################

ALTER TABLE legchecks ADD KEY IF NOT EXISTS ix_legchecks_runleg (runid, legid);
ALTER TABLE legchecks DROP FOREIGN KEY IF EXISTS fk_legchecks_requirement;
ALTER TABLE legchecks DROP INDEX IF EXISTS ux_legchecks;
ALTER TABLE legchecks
  MODIFY COLUMN requirementid VARCHAR(36) NULL,
  ADD COLUMN IF NOT EXISTS rulecode    VARCHAR(64)  NULL AFTER requirementid,
  ADD COLUMN IF NOT EXISTS rulename    VARCHAR(160) NULL AFTER rulecode,
  ADD COLUMN IF NOT EXISTS ruleversion INT          NULL AFTER rulename,
  ADD COLUMN IF NOT EXISTS approved    TINYINT(1)   NULL AFTER ruleversion;
