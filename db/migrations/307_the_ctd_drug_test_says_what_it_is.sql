-- ################################################################################################
-- # 307 - the CTD drug testing requirement is named for the thing that answers it.
-- #
-- # "Drug and alcohol testing records (safety-sensitive)" described a program, and beside the
-- # company's own non-DOT screen it read as a second drug test nobody could tell apart from the
-- # first. What answers it is the regulated pre-employment test, so that is what it is called.
-- ################################################################################################

UPDATE compliancerules SET name = 'Pre-employment drug test (CTD)'
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'FL_TD_DRUG_TESTING';
