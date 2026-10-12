-- ################################################################################################
-- # 023 - split the document catalog by who holds it.
-- #
-- # subject  'company'  paperwork the company itself must hold (Company Compliance)
-- #          'driver'   paperwork that lives in each driver's file, including everything a driver
-- #                     signs - kept here for Driver Compliance, and off the company list.
-- #
-- # Also sharpens the USDOT row: the federal number follows the commercial-motor-vehicle definition
-- # in 49 CFR 390.5 (interstate, and over 10,000 lb GVWR or designed for more than 8 passengers
-- # including the driver for compensation). Intrastate USDOT numbers are a State matter.
-- ################################################################################################
ALTER TABLE compliancedocs
    ADD COLUMN IF NOT EXISTS subject VARCHAR(8) NOT NULL DEFAULT 'company' AFTER jurisdiction;

ALTER TABLE compliancedocs
    ADD CONSTRAINT IF NOT EXISTS ck_compliancedocs_subject CHECK (subject IN ('company', 'driver'));

UPDATE compliancedocs SET subject = 'driver' WHERE driversign = 1;

UPDATE compliancedocs SET
    appliesif = 'Interstate operation with a vehicle over 10,000 lb GVWR, or designed for more than 8 passengers including the driver for compensation',
    description = 'Registration with FMCSA, kept current by the biennial update. A purely intrastate operation needs no federal number, though many States require their own USDOT registration.'
    WHERE jurisdiction = 'US' AND code = 'USDOT_MCS150';
