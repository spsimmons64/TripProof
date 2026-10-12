-- ################################################################################################
-- # 034 - take out documents that appear twice, and rows that are only a pointer to State law.
-- #
-- # FL_DRIVER_LICENSE was the same document as the federal DRIVER_LICENSE_COPY: a copy of the
-- # driver's license. Florida's contribution is the threshold at which it must be a CDL, which is a
-- # fact about the licence class, not a second document - it moves into the intrastate row's note.
-- #
-- # FINGERPRINT_SCREENING and WORKERS_COMP_COI sat in the federal layer while naming State law as
-- # their authority. They are what a State demands, so they belong to State layers: Florida already
-- # carries both (FL_LEVEL2_DRIVER, FL_WORKERS_COMP), and other States will as they are loaded.
-- #
-- # Kept as a pair on purpose: the federal auto liability certificate (what brokers and insurers
-- # want everywhere) and Florida's row, which adds the statutory minimum limits. Its name now says
-- # so. Likewise the FMCSA medical certificate and Florida's bus transit examination are different
-- # examinations under different standards, and both can be owed.
-- ################################################################################################
UPDATE compliancedocs SET description = CONCAT(description,
    ' Florida requires a CDL only at 26,001 lb GVWR, more than 15 passengers including the driver, or placarded hazmat (F.S. 322.01(8), 322.53), so most NEMT vans are driven on a Class E license.')
    WHERE jurisdiction = 'FL' AND subject = 'driver' AND code = 'FL_INTRASTATE_DQ';

DELETE FROM compliancedocs WHERE jurisdiction = 'FL' AND subject = 'driver' AND code = 'FL_DRIVER_LICENSE';
DELETE FROM compliancedocs WHERE jurisdiction = 'US' AND subject = 'driver' AND code = 'FINGERPRINT_SCREENING';
DELETE FROM compliancedocs WHERE jurisdiction = 'US' AND subject = 'company' AND code = 'WORKERS_COMP_COI';

UPDATE compliancedocs SET
    name = 'For-hire auto liability - Florida minimum limits',
    description = 'Florida sets the limits federal law does not: $125,000 per person, $250,000 per incident, $50,000 property damage. The certificate itself is the one on the federal list; this row is the floor Florida puts under it.'
    WHERE jurisdiction = 'FL' AND code = 'FL_FORHIRE_INSURANCE';
