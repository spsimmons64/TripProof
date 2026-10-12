-- ################################################################################################
-- # 056 - Level 2 screening is conditional: Chapter 435 does not reach a driver by itself.
-- #
-- # s. 435.04 defines the screening - fingerprints, FDLE state criminal history, and an FBI national
-- # check - but it applies to a person only when some other law says they must be screened under
-- # that section. For an NEMT driver that is usually s. 408.809, which reaches people providing
-- # direct personal care or services, or with specified access to clients or their property, at an
-- # AHCA-licensed provider; a Department of Elder Affairs programme or a broker's contract can do
-- # the same.
-- ################################################################################################
UPDATE compliancedocs
   SET obligation    = 'conditional',
       appliesif     = 'Another law reaches this driver: direct care or specified client access at an '
                       'AHCA-licensed provider (s. 408.809), a Department of Elder Affairs programme '
                       '(s. 430.0402), or a broker or contract that requires it',
       legalcitation = 'F.S. 435.04; F.S. 408.809; F.S. 430.0402',
       description   = 'Fingerprint-based screening: Florida criminal history through FDLE and a national '
                       'check through the FBI. Chapter 435 defines the screening but does not itself '
                       'require it of every NEMT driver - it applies when another law says this person '
                       'must be screened under that section.'
 WHERE subject = 'driver' AND code = 'FL_LEVEL2_DRIVER';

UPDATE accountqualifications
   SET obligation = 'conditional'
 WHERE catalog = 1 AND code = 'FL_LEVEL2_DRIVER' AND obligation = 'required';
