-- ################################################################################################
-- # 032 - Florida driver documents (jurisdiction 'FL', subject 'driver').
-- #
-- # What Florida adds to a driver's file, on top of the federal layer and without repeating it.
-- # Most of it arrives through the Transportation Disadvantaged programme: rule 41-2.006 binds the
-- # Community Transportation Coordinator and every operator under it to the FDOT bus transit safety
-- # standards in chapter 14-90, which is where Florida's own medical examination and driving rules
-- # live - they reach drivers of ordinary vans, not only CDL holders.
-- #
-- # Florida's CDL line is its own: 26,001 lb GVWR, more than 15 passengers including the driver, or
-- # placarded hazmat (F.S. 322.01(8), 322.53). A 15-passenger NEMT van needs only a Class E licence.
-- #
-- # Checked against the statutes (flsenate.gov) and the adopted rule text (flrules.org) 2026-09-22.
-- ################################################################################################
SET @fs = 'https://www.flsenate.gov/Laws/Statutes/2024/';
SET @fac = 'https://www.flrules.org/gateway/ruleNo.asp?id=';

INSERT IGNORE INTO compliancedocs
    (recordid, jurisdiction, subject, code, name, obligation, requiredfor, category, expires, driversign, renewal,
     appliesif, description, legalcitation, authority, sourceurl, sortorder)
VALUES
-- Every driver, CDL or not -----------------------------------------------------------------------
('c0555555-0000-4000-8000-000000000001', 'FL', 'driver', 'FL_DRIVER_LICENSE', 'Florida driver licence (Class E unless a CDL is required)', 'required', 'both', 'licensing', 1, 0,
 'Expiry printed on the licence', '',
 'Florida requires a CDL only at 26,001 lb GVWR, more than 15 passengers including the driver, or placarded hazmat - so most NEMT vans are driven on a Class E licence.',
 'F.S. 322.53; F.S. 322.01(8)', 'Florida DHSMV', CONCAT(@fs, '322.53'), 10),
('c0555555-0000-4000-8000-000000000002', 'FL', 'driver', 'FL_TRANSIT_MEDICAL', 'Bus transit medical examination', 'required', 'both', 'licensing', 1, 0,
 'Before hire, then at least every 2 years, and again before returning to duty after time off for illness or injury',
 'Operates under a Community Transportation Coordinator''s coordinated system',
 'Florida''s own medical standard, examined by a Florida-licensed physician, physician assistant or ARNP. It applies to van drivers, unlike the federal certificate, which follows the commercial-vehicle line.',
 'F.A.C. 14-90.0041', 'FDOT', CONCAT(@fac, '14-90.0041'), 20),
('c0555555-0000-4000-8000-000000000003', 'FL', 'driver', 'FL_LICENSE_STATUS_NOTICE', 'Licence suspension notice undertaking', 'required', 'both', 'licensing', 0, 1,
 'On hire; the driver must report a suspension by the end of the next business day',
 'Operates under a Community Transportation Coordinator''s coordinated system',
 'No one may drive on a suspended, cancelled or revoked licence, and the driver must tell the employer at once. Signed so the duty is on record.',
 'F.A.C. 14-90.006(1)', 'FDOT', CONCAT(@fac, '14-90.006'), 30),
('c0555555-0000-4000-8000-000000000004', 'FL', 'driver', 'FL_TD_DRUG_TESTING', 'Drug and alcohol testing records (safety-sensitive position)', 'required', 'both', 'screening', 0, 0,
 'Pre-employment, random, post-accident and on reasonable suspicion',
 'Carries Transportation Disadvantaged trips in a county''s coordinated system',
 'The coordinated system applies testing to safety-sensitive posts whether or not the driver holds a CDL.',
 'F.A.C. 41-2.006(4)(a)', 'Commission for the Transportation Disadvantaged', CONCAT(@fac, '41-2.006'), 40),
('c0555555-0000-4000-8000-000000000005', 'FL', 'driver', 'FL_SSPP_DRIVER_RECORDS', 'Driver selection and training records under the System Safety Program Plan', 'required', 'both', 'training', 0, 0,
 'Kept current under the operator''s safety plan',
 'Operates under a Community Transportation Coordinator''s coordinated system',
 'The plan must cover driver selection, driving requirements and driver training, including how to approach and leave a stop safely.',
 'F.A.C. 14-90.004(1)', 'FDOT', CONCAT(@fac, '14-90.004'), 50),
('c0555555-0000-4000-8000-000000000006', 'FL', 'driver', 'FL_HOURS_OF_SERVICE', 'Hours of service record (12-hour driving, 16-hour duty)', 'required', 'both', 'safety', 0, 0,
 'Kept per driver, per day', 'Operates under a Community Transportation Coordinator''s coordinated system',
 'No more than 12 hours driving in 24, no driving after 16 hours on duty, and 8 consecutive hours off before driving again.',
 'F.A.C. 14-90.006(3)', 'FDOT', CONCAT(@fac, '14-90.006'), 60),
('c0555555-0000-4000-8000-000000000007', 'FL', 'driver', 'FL_LEVEL2_DRIVER', 'Level 2 background screening (driver)', 'required', 'both', 'screening', 1, 0,
 'Fingerprints are retained on a 5-year renewal basis',
 'Serves clients under a Department of Elder Affairs programme, or the broker or AHCA contract requires it',
 'Fingerprint-based screening under chapter 435. Required by statute for direct service providers to the elderly; broker and AHCA contracts extend it to NEMT drivers more widely.',
 'F.S. 430.0402; F.S. 435.04', 'AHCA / Department of Elder Affairs', CONCAT(@fs, '430.0402'), 70),
-- CDL drivers --------------------------------------------------------------------------------------
('c0555555-0000-4000-8000-000000000008', 'FL', 'driver', 'FL_INTRASTATE_DQ', 'Intrastate driver qualification records (49 CFR 391)', 'conditional', 'cdl', 'employment', 0, 0,
 'As parts 382-386 and 390-397 required on December 31, 2023',
 'Drives a vehicle of 10,000 lb GVWR or more, or designed for more than 15 passengers including the driver, wholly inside Florida',
 'Florida applies the federal motor carrier rules to intrastate driving, so the qualification file, MVRs and medical certificate are owed even on trips that never leave the State - with Florida''s own hours limits.',
 'F.S. 316.302(1)(b); F.S. 316.003', 'Florida Highway Patrol', CONCAT(@fs, '316.302'), 80);
