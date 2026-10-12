-- ################################################################################################
-- # 088 - the pre-employment controlled substances test is a hiring gate, not an on-hire errand.
-- #
-- # 49 CFR 382.301(a): a driver may not perform any safety-sensitive function until the employer
-- # has received a negative pre-employment controlled substances test result. So it is not
-- # something the office gets round to after taking someone on - it is one of the things the
-- # hiring decision waits on, and it belongs with the rest of them.
-- #
-- # It was already in the catalog, required of commercial drivers; only its stage was wrong, which
-- # is why it never showed among the items a driver is held up by.
-- ################################################################################################
UPDATE compliancedocs
   SET stage = 'prehire',
       whendue = 'Before the driver first performs a safety-sensitive function'
 WHERE code = 'PREEMPLOYMENT_DRUG_TEST' AND subject = 'driver';

-- Accounts carry their own copy of the list, so theirs moves with it - except where an account has
-- decided the requirement does not reach it at all, which is their decision to keep.
UPDATE accountqualifications
   SET stage = 'prehire'
 WHERE code = 'PREEMPLOYMENT_DRUG_TEST' AND subject = 'driver' AND applies <> 'off';
