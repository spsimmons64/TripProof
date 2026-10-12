-- ################################################################################################
-- # 116 - the exclusion requirement covers every list it is named after.
-- #
-- # The rule is called "Exclusion screening - OIG LEIE and SAM.gov" and its evidence pointed at
-- # `exclusioncheck:OIG_LEIE`, so it read the OIG list and nothing else. A driver recorded as
-- # confirmed excluded on SAM showed a green tick, because their OIG check was clear.
-- #
-- # Dropping the list from the source means "any list this driver has been screened against" -
-- # which is what the requirement always claimed to be.
-- ################################################################################################
UPDATE compliancerules SET evidencesource = 'exclusioncheck'
 WHERE code = 'EXCLUSION_CHECK_DRIVER' AND effectiveto IS NULL;
