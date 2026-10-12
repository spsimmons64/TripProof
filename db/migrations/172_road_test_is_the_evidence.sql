-- ################################################################################################
-- # 172 - the road test answers its own requirement.
-- #
-- # The rule read `credential:ROAD_TEST` - a document somebody uploads. So an examiner could take a
-- # driver out, fail them, sign the evaluation, and the requirement would not notice: it was
-- # watching a credential nobody creates, and the only thing that ever turned it green was the
-- # 391.33 equivalence on a CDL.
-- #
-- # The test IS the evidence. A pass qualifies, a fail disqualifies, and the certificate is the
-- # document the test carries rather than a separate thing to be filed.
-- ################################################################################################

UPDATE compliancerules
   SET evidencesource = 'roadtest'
 WHERE subject = 'driver' AND code = 'ROAD_TEST' AND effectiveto IS NULL;
