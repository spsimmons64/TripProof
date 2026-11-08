-- ################################################################################################
-- # 412 - rules loaded from a requirements file wait, staged, until somebody approves them.
-- #
-- # A staged rule is stored as not yet in force (effectiveto in the distant past), so every query
-- # that reads the rules in force - the trip check, the driver's file, dispatch - passes over it,
-- # and nothing on any account changes because a file was loaded. Rule Review lists staged rules;
-- # approving one brings it into force and ends the rule it replaces in the same act, so a
-- # protection in force never lapses while its replacement waits.
-- #
-- # `sourceref` is the requirement's own id in the file it came from (MED-DRV-001), kept when the
-- # rule takes over the code of the rule it replaces.
-- ################################################################################################

ALTER TABLE compliancerules
  ADD COLUMN IF NOT EXISTS staged    TINYINT(1)  NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS sourceref VARCHAR(32) NULL;
