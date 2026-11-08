-- ################################################################################################
-- # 406 - rules every company owes under State or local law, filed under State NEMT.
-- #
-- # 405 sorted rules with no category by jurisdiction, and these are written once for every State
-- # (jurisdiction US) though no federal rule asks for any of them.
-- ################################################################################################

UPDATE compliancerules SET authoritycategory = 'STATE_NEMT'
 WHERE code IN ('WORKERS_COMP', 'BUSINESS_LICENSE', 'COPEC', 'VEHICLE_REGISTRATION',
                'VEHICLE_INSURANCE_CARD')
   AND accountid IS NULL;
