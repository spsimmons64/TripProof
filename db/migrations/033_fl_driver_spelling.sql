-- ################################################################################################
-- # 033 - US spelling and a clearer name for two Florida driver rows added in 032.
-- ################################################################################################
UPDATE compliancedocs SET
    name = 'Florida driver license (Class E unless a CDL is required)',
    description = 'Florida requires a CDL only at 26,001 lb GVWR, more than 15 passengers including the driver, or placarded hazmat - so most NEMT vans are driven on a Class E license.',
    renewal = 'Expiry printed on the license'
    WHERE jurisdiction = 'FL' AND code = 'FL_DRIVER_LICENSE';

UPDATE compliancedocs SET
    name = 'License suspension reporting acknowledgement',
    description = 'No one may drive on a suspended, cancelled or revoked license, and the driver must tell the employer at once. Signed so the duty is on record.'
    WHERE jurisdiction = 'FL' AND code = 'FL_LICENSE_STATUS_NOTICE';
