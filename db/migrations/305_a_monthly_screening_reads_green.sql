-- ################################################################################################
-- # 305 - the OIG screening reads green between monthly runs.
-- #
-- # It stands 31 days and warned at 30, so it went amber the day after every screening and stayed
-- # that way. The daily job picks up each new list on its own; amber is kept for the last day.
-- # 0 cannot be used - the engine reads it as "no setting" and falls back to its 30-day default.
-- ################################################################################################

UPDATE compliancerules SET warndays = 1
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'EXCLUSION_OIG_LEIE';
