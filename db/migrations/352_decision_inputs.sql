-- What each trip decision was made FROM - the facts assembled for the trip and where every
-- requirement stood, on which record - kept beside the rule hashes (rulesread) and engine version,
-- so a decision can be replayed against exactly what it read.
ALTER TABLE tripeligibility
  ADD COLUMN IF NOT EXISTS factsread MEDIUMTEXT NULL AFTER engineversion,
  ADD COLUMN IF NOT EXISTS standingread MEDIUMTEXT NULL AFTER factsread;
