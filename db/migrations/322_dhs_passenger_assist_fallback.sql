-- ################################################################################################
-- # 322 - the DHS passenger assistance rule accepts the combined securement certificate, as the
-- # platform's passenger assistance rule does. It lost that fallback when it was copied in 321.
-- ################################################################################################

UPDATE compliancerules SET alternatesource = 'credential:WHEELCHAIR_SECUREMENT'
 WHERE code = 'DHS_PASSENGER_ASSIST' AND accountid IS NULL AND effectiveto IS NULL;
