-- ################################################################################################
-- # 201 - the SPE requirement should not reach drivers it cannot be asked about.
-- #
-- # It is conditioned on what the driving record's medical block says, and that block only exists
-- # on a commercial record. For a driver who operates nothing commercial there is no record to
-- # read, so the fact comes back unknown and the requirement sat in "Waiting On An Answer From The
-- # Company" on every non-commercial driver in the account - asking about a certificate that
-- # nothing on their file could ever mention.
-- #
-- # A definite no is the right answer there, and the operation ticks already give one.
-- ################################################################################################

UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"driver.cmv","is":true},'
                     '{"fact":"driver.spevariance","is":true}]}'
 WHERE subject = 'driver' AND code = 'SPE_CERTIFICATE' AND effectiveto IS NULL;
