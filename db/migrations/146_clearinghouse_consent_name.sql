-- ################################################################################################
-- # 146 - the Clearinghouse consent is named for what it is.
-- #
-- # 49 CFR 382.701(b)(2) is not a general permission: it is the driver's specific electronic
-- # consent, given in the Clearinghouse itself, for one full query. "Clearinghouse query consent -
-- # signed by the driver" read as though it were a form the office holds, which is the one thing it
-- # is not.
-- ################################################################################################

UPDATE compliancerules
   SET name = 'Clearinghouse Full Query - Electronic Driver Consent'
 WHERE code = 'CLEARINGHOUSE_CONSENT' AND subject = 'driver';
