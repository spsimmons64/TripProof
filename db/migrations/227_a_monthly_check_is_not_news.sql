-- ################################################################################################
-- # 227 - a check that re-runs every month is not a thing "running out".
-- #
-- # The exclusion screenings showed on the dashboard as expiring - four drivers, every month, for
-- # ever. They are not a certificate with an end date somebody must go and renew: they are a
-- # standing monthly check, and the only event worth anybody's attention is a HIT. Listing the
-- # renewal of a routine check beside an expired medical certificate is how a dashboard teaches
-- # people to ignore it.
-- #
-- # `scheduled` marks a requirement that comes round on its own. It changes nothing about whether
-- # the rule is met, when it is due, or what the driver's own page shows - the date is still there,
-- # still arithmetic, still red the day it lapses. It only keeps the routine turn of the cycle off
-- # the screen that is meant to carry exceptions.
-- ################################################################################################

ALTER TABLE compliancerules
  ADD COLUMN IF NOT EXISTS scheduled TINYINT(1) NOT NULL DEFAULT 0 AFTER recurrence;

UPDATE compliancerules SET scheduled = 1
 WHERE subject = 'driver' AND effectiveto IS NULL
   AND code IN ('EXCLUSION_OIG_LEIE', 'EXCLUSION_SAM_GOV');
