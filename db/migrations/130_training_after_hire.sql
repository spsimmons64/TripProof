-- ################################################################################################
-- # 130 - the trainings are owed after hire, not before it.
-- #
-- # Passenger assistance, wheelchair securement, bloodborne pathogens and HIPAA are things an
-- # employer trains a driver to do. Asking for them before hire is asking an applicant to arrive
-- # already trained by somebody else, and it put four permanent grey questions in front of every
-- # hiring decision - none of which is a reason not to hire.
-- #
-- # They are still required, and still blocking once they are due. What changes is when they are
-- # asked for, which is what `duestage` says.
-- ################################################################################################

UPDATE compliancerules
   SET duestage = 'athire'
 WHERE subject = 'driver'
   AND code IN ('PASS_TRAINING', 'SECUREMENT_TRAINING_CERT', 'BBP_TRAINING',
                'HIPAA_TRAINING_DRIVER');
