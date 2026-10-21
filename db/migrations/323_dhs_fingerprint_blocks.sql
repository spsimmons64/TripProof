-- ################################################################################################
-- # 323 - the DHS fingerprint check blocks. It was copied from the Level 2 rule, which a broker
-- # asks for and does not block; DHS requires the national check before a driver transports anyone.
-- ################################################################################################

UPDATE compliancerules SET blocking = 1
 WHERE code = 'DHS_FINGERPRINT' AND accountid IS NULL AND effectiveto IS NULL;
