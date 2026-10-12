-- ################################################################################################
-- # 057 - the abuse registry check is not a document Florida asks an NEMT driver for.
-- #
-- # 59G-4.330, the rule for Medicaid non-emergency transportation providers, does not ask for a
-- # separate adult protective or abuse registry check on every driver. Florida does hold records of
-- # reports of abuse, neglect or exploitation of vulnerable adults under Chapter 415, but they are
-- # confidential and access is restricted by s. 415.107 - they are not a registry an employer
-- # searches while credentialing a driver.
-- #
-- # It stays on the catalog because a broker or a contract can still ask for one, and because a
-- # company that wants it should be able to keep it; it stays recommended, and it says why.
-- ################################################################################################
UPDATE compliancedocs
   SET obligation    = 'recommended',
       appliesif     = 'A broker or a contract asks for one',
       legalcitation = 'F.S. 415.107',
       renewal       = 'Only as a broker or contract requires',
       validdays     = NULL,
       description   = 'Not a standalone requirement for a Florida NEMT driver: rule 59G-4.330 does not ask '
                       'for one, and the Chapter 415 records of abuse, neglect or exploitation of vulnerable '
                       'adults are confidential, with access restricted by s. 415.107 rather than open to an '
                       'employer credentialing a driver.'
 WHERE subject = 'driver' AND code = 'ABUSE_REGISTRY_CHECK';

UPDATE accountqualifications
   SET obligation = 'recommended', validdays = NULL
 WHERE catalog = 1 AND code = 'ABUSE_REGISTRY_CHECK';
