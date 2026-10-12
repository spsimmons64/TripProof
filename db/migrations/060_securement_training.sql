-- ################################################################################################
-- # 060 - wheelchair securement training follows the equipment and the passengers.
-- #
-- # Florida's bus transit safety rules require a covered driver to be trained and tested on wheelchair
-- # lifts and other special equipment, on passenger assistance and securement, and to be familiar
-- # with the lift and the restraining devices. AHCA's Medicaid transportation material asks for the
-- # same training. Both reach a driver who carries passengers in wheelchairs or works accessible
-- # equipment - not a driver who never does.
-- ################################################################################################
UPDATE compliancedocs
   SET obligation    = 'conditional',
       appliesif     = 'The driver carries passengers using wheelchairs, or operates wheelchair-accessible '
                       'equipment',
       legalcitation = 'F.A.C. 14-90.004(1); 49 CFR 37.173',
       renewal       = 'Per the training provider; two years is common',
       validdays     = 730,
       description   = 'Training and testing on the wheelchair lift and other special equipment, on passenger '
                       'assistance, and on securing a wheelchair and its occupant, including familiarity with '
                       'the restraining devices in the vehicle the driver works.'
 WHERE subject = 'driver' AND code = 'SECUREMENT_TRAINING_CERT';

UPDATE accountqualifications
   SET obligation = 'conditional'
 WHERE catalog = 1 AND code = 'SECUREMENT_TRAINING_CERT' AND obligation = 'required';
