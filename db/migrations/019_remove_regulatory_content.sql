-- ################################################################################################
-- # 019 - start over on regulatory content.
-- #
-- # Removed: every rule set and requirement (and the trip checks made against them), the regulatory
-- # source map and its change history, the regulations library, cited sources, research profiles,
-- # and company operating profiles.
-- # Kept: the credential vault, drivers, vehicles, trips, credential types, brokers, and the
-- # trip-checking engine (rulesets / requirements / evaluationruns / legchecks), now with no rules.
-- # Evaluation runs are kept so existing audit packets still reference the run they were built from.
-- ################################################################################################
DELETE FROM legchecks;
UPDATE trips SET lastrunid = NULL;
DELETE FROM requirements;
DELETE FROM rulesets;

ALTER TABLE requirements DROP FOREIGN KEY IF EXISTS fk_requirements_regulation;
ALTER TABLE requirements DROP FOREIGN KEY IF EXISTS fk_requirements_source;
ALTER TABLE rulesets DROP FOREIGN KEY IF EXISTS fk_rulesets_source;
ALTER TABLE regulations DROP FOREIGN KEY IF EXISTS fk_regulations_source;

DROP TABLE IF EXISTS regchanges;
DROP TABLE IF EXISTS regsources;
DROP TABLE IF EXISTS jurisdictions;
DROP TABLE IF EXISTS lawprofiles;
DROP TABLE IF EXISTS stateprograms;
DROP TABLE IF EXISTS companyprofiles;
DROP TABLE IF EXISTS regulations;
DROP TABLE IF EXISTS sources;

ALTER TABLE credentialtypes DROP COLUMN IF EXISTS regulationid;
ALTER TABLE credentialtypes DROP COLUMN IF EXISTS sourceid;
