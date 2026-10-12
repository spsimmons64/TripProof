-- ################################################################################################
-- # 174 - the medical certificate and the road test move in front of the hiring decision.
-- #
-- # Migration 143 split them out as `predrive` on the reasoning that 391.43 is about being
-- # physically qualified to drive and 391.31 about demonstrating skill - neither is a reason to
-- # decline somebody as an employee, and FMCSA is explicit that a road test may happen before hire.
-- #
-- # True, and not how this office works. Both are things somebody wants settled while they are
-- # deciding, because a driver who cannot pass a physical or a road test is not a driver they can
-- # use - and a requirement that only appears after the decision is one nobody sees in time.
-- #
-- # The Florida bus transit medical stays with them, since it answers the same question under
-- # F.A.C. 14-90.0041.
-- ################################################################################################

UPDATE compliancerules
   SET duestage = 'prehire'
 WHERE subject = 'driver' AND effectiveto IS NULL
   AND code IN ('MEDICAL_CERT', 'ROAD_TEST', 'FL_TRANSIT_MEDICAL');
