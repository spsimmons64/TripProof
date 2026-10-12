-- ################################################################################################
-- # 089 - the day a driver went into the random testing pool.
-- #
-- # 49 CFR 382.305 tests a pool, not a person: the carrier draws names from everyone subject to
-- # testing, at the required annual rate. So what the file has to be able to say about one driver
-- # is when they joined that pool - which is the date an auditor asks for, and the date that shows
-- # a driver was not quietly left out of it.
-- ################################################################################################
ALTER TABLE drivers ADD COLUMN randompoolon DATE NULL AFTER chapter1490;
