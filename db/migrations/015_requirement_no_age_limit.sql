-- ################################################################################################
-- # 015 - a requirement can say "no age limit": the credential only has to be current (unexpired,
-- # unrevoked), whatever its type's default freshness. Research-loaded rules use this when the
-- # official source states no refresh period, so TripProof's defaults are never passed off as law.
-- ################################################################################################
ALTER TABLE requirements ADD COLUMN IF NOT EXISTS noagelimit TINYINT(1) NOT NULL DEFAULT 0 AFTER maxagedays;
