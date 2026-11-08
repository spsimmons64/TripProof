-- ################################################################################################
-- # 411 - the MCS-150 biennial update is 49 CFR 390.19T.
-- #
-- # 390.19 is the identification report for certain Mexico-domiciled carriers. The filing every
-- # registered carrier makes, and its biennial schedule, are in the temporary section 390.19T.
-- ################################################################################################

UPDATE compliancerules
   SET citation = REPLACE(citation, '49 CFR 390.19;', '49 CFR 390.19T;')
 WHERE code = 'USDOT_AUTHORITY' AND accountid IS NULL AND citation LIKE '49 CFR 390.19;%';
UPDATE compliancerules
   SET citation = '49 CFR 390.19T'
 WHERE code = 'MCS150' AND accountid IS NULL AND citation = '49 CFR 390.19';
