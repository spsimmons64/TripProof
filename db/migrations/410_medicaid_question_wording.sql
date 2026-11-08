-- ################################################################################################
-- # 410 - the Medicaid question said what federal law does not.
-- #
-- # It promised "exclusion screening against the OIG list every month". 42 U.S.C. 1396a(a)(87)
-- # requires that a Medicaid NEMT driver is not excluded and holds a valid license; it sets no
-- # screening frequency. Monthly comes from States (42 CFR 455.436 binds the State, for providers)
-- # and from brokers, and is carried by their own requirements.
-- ################################################################################################

UPDATE companyquestions
   SET help = 'Turns on the federal Medicaid NEMT requirements - each driver not excluded from federal health care programs (the OIG exclusion list) and holding a valid driver''s license - and the Medicaid program rules of the states you carry for. 42 U.S.C. 1396a(a)(87).'
 WHERE code = 'MEDICAID_TRIPS';
