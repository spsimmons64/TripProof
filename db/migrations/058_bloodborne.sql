-- ################################################################################################
-- # 058 - bloodborne pathogens training follows the duties, not the job title.
-- #
-- # OSHA's standard, 29 CFR 1910.1030, reaches an employee with occupational exposure: contact with
-- # blood or other potentially infectious materials that is reasonably anticipated from what they
-- # are asked to do. Driving a passenger to an appointment does not on its own bring a driver under
-- # it; particular assistance duties can. So this is conditional on the duties assigned, and the
-- # company is the one who knows what those are.
-- #
-- # Where it applies, the training is given at assignment and at least once a year after that.
-- ################################################################################################
UPDATE compliancedocs
   SET obligation    = 'conditional',
       appliesif     = 'The duties assigned to this driver reasonably anticipate contact with blood or other '
                       'potentially infectious materials',
       legalcitation = '29 CFR 1910.1030',
       renewal       = 'At assignment, then at least annually while it applies',
       validdays     = 365,
       description   = 'OSHA training for a driver with occupational exposure. Transporting a passenger to an '
                       'appointment does not by itself bring a driver under the standard; assistance duties '
                       'that make contact with blood or other potentially infectious materials reasonably '
                       'foreseeable do.'
 WHERE subject = 'driver' AND code = 'BBP_TRAINING';

UPDATE accountqualifications
   SET obligation = 'conditional'
 WHERE catalog = 1 AND code = 'BBP_TRAINING' AND obligation = 'required';
