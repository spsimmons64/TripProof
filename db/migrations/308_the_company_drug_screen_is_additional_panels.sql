-- ################################################################################################
-- # 308 - the company's own drug screen is named for why it exists beside the regulated one.
-- #
-- # Next to "Pre-employment drug test (CTD)", "non-DOT" said what it is not. A company or broker
-- # asks for it to screen for more than the regulated panel, so that is what it is called.
-- ################################################################################################

UPDATE compliancerules SET name = 'Pre-employment drug screen (additional panels)'
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'NONDOT_DRUG_SCREEN';
