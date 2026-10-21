-- ################################################################################################
-- # 306 - the SAM.gov screening runs daily, against GSA's daily exclusions extract.
-- #
-- # A screening stands 3 days. A day the download fails changes nothing on its own; two in a row
-- # and the requirement goes amber, three and it is red - so a driver is never shown as cleared
-- # against a list TripProof could not fetch.
-- ################################################################################################

UPDATE compliancerules SET recurrencedays = 3, warndays = 1
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'EXCLUSION_SAM_GOV';
