-- ################################################################################################
-- # 346 - Georgia Medicaid NEMT training is due before driving (2026-10-22).
-- #
-- # DCH Part II (October 2026) 916.1: driver training, first aid, and spill kit and biohazard
-- # training are completed "prior to driving under the NEMT program", with passenger assistance,
-- # safety and sensitivity, and defensive driving within driver training (916.1.1-916.1.3). 916.2
-- # lets a driver who has never been trained finish within 90 days of assignment, but does not say
-- # which courses may be outstanding while they carry passengers, and the broker may set its own
-- # approved standard. Every new driver was being given the 90 days automatically. Until Verida
-- # confirms in writing what the allowance covers, the training is owed before driving.
-- ################################################################################################
UPDATE compliancerules
   SET duestage = 'predrive', duedays = NULL,
       duetext = 'Before driving under the NEMT program (DCH 916.1)',
       note = 'DCH 916.2 allows 90 days from assignment for a driver never trained before; not applied until the broker confirms in writing which training it covers.'
 WHERE accountid IS NULL AND effectiveto IS NULL
   AND code IN ('GA_NET_DRIVER_TRAINING', 'GA_NET_FIRST_AID', 'GA_NET_SPILL_KIT',
                'GA_NET_PASSENGER_ASSIST', 'GA_NET_SAFETY_SENSITIVITY');
