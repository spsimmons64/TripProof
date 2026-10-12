-- ################################################################################################
-- # 035 - Vehicle Compliance: the paper that has to exist for each vehicle.
-- #
-- # A third catalog beside company and driver, with the company's three buckets (required /
-- # conditional / recommended) rather than the driver's CDL split, because what a vehicle owes turns
-- # on the vehicle: whether it carries a lift, and whether it is over the commercial line.
-- #
-- # Federal law says little about an ordinary NEMT van: parts 393 and 396 reach commercial motor
-- # vehicles, and part 38 reaches accessible vehicles when they are bought. Registration, titling
-- # and periodic inspection are State matters, so they sit in the Florida layer.
-- #
-- # The preventive maintenance row moves here from the company catalog, where it never belonged.
-- # Citations checked against eCFR, flsenate.gov and the adopted rule text on flrules.org 2026-09-22.
-- ################################################################################################
ALTER TABLE compliancedocs DROP CONSTRAINT IF EXISTS ck_compliancedocs_subject;
ALTER TABLE compliancedocs
    ADD CONSTRAINT IF NOT EXISTS ck_compliancedocs_subject CHECK (subject IN ('company', 'driver', 'vehicle'));

UPDATE compliancedocs SET subject = 'vehicle', sortorder = 300
    WHERE jurisdiction = 'US' AND code = 'VEHICLE_MAINTENANCE';

SET @ecfr = 'https://www.ecfr.gov/current/title-';
SET @fs = 'https://www.flsenate.gov/Laws/Statutes/2024/';
SET @fac = 'https://www.flrules.org/gateway/ruleNo.asp?id=';

INSERT IGNORE INTO compliancedocs
    (recordid, jurisdiction, subject, code, name, obligation, category, expires, driversign, renewal, appliesif,
     description, legalcitation, authority, sourceurl, sortorder)
VALUES
-- Federal, required if ---------------------------------------------------------------------------
('c0666666-0000-4000-8000-000000000001', 'US', 'vehicle', 'LIFT_OPERATIVE', 'Wheelchair lift and securement maintenance record', 'conditional', 'inspection', 0, 0,
 'Repaired promptly when out of order', 'Vehicle carries a lift, ramp or securement system',
 'The ADA requires accessibility features to be kept in operative condition, so the repair history is the proof.',
 '49 CFR 37.161', 'U.S. DOT (ADA)', CONCAT(@ecfr, '49/section-37.161'), 10),
('c0666666-0000-4000-8000-000000000002', 'US', 'vehicle', 'PART38_SPECS', 'Accessible vehicle specification record (Part 38)', 'conditional', 'inspection', 0, 0,
 'At purchase or lease', 'An accessible vehicle was bought or leased',
 'Lift rated 600 lb and interlocked so the vehicle cannot move unless stowed, securement area 30 x 48 in, lap and shoulder belts.',
 '49 CFR 38.23', 'U.S. DOT (ADA)', CONCAT(@ecfr, '49/section-38.23'), 20),
('c0666666-0000-4000-8000-000000000003', 'US', 'vehicle', 'PERIODIC_INSPECTION', 'Periodic (annual) inspection report', 'conditional', 'inspection', 1, 0,
 'At least every 12 months; keep the report 14 months', 'Commercial motor vehicle',
 'Inspection against appendix A to part 396 by a qualified inspector.',
 '49 CFR 396.17; 49 CFR 396.21(b)', 'FMCSA', CONCAT(@ecfr, '49/section-396.17'), 30),
('c0666666-0000-4000-8000-000000000004', 'US', 'vehicle', 'DVIR', 'Driver vehicle inspection reports (DVIR)', 'conditional', 'inspection', 0, 0,
 'At the end of each day''s work; keep 3 months', 'Commercial motor vehicle',
 'The driver''s written report on each vehicle operated, with the repair certification where a defect is found.',
 '49 CFR 396.11', 'FMCSA', CONCAT(@ecfr, '49/section-396.11'), 40),
('c0666666-0000-4000-8000-000000000005', 'US', 'vehicle', 'MAINTENANCE_FILE', 'Systematic inspection, repair and maintenance file', 'conditional', 'inspection', 0, 0,
 'Keep 1 year, and 6 months after the vehicle leaves the carrier''s control', 'Commercial motor vehicle',
 'Vehicle identification, the schedule of inspections due, the repair history, and tests of pushout windows and emergency doors on buses.',
 '49 CFR 396.3(b), (c)', 'FMCSA', CONCAT(@ecfr, '49/section-396.3'), 50),
('c0666666-0000-4000-8000-000000000006', 'US', 'vehicle', 'EMERGENCY_EQUIPMENT', 'Emergency equipment on board', 'conditional', 'safety', 0, 0,
 'Checked on the daily inspection', 'Commercial motor vehicle (truck, tractor or bus)',
 'Fire extinguisher, spare fuses where needed, and warning devices for a stopped vehicle.',
 '49 CFR 393.95', 'FMCSA', CONCAT(@ecfr, '49/section-393.95'), 60),
('c0666666-0000-4000-8000-000000000007', 'US', 'vehicle', 'USDOT_MARKING', 'USDOT number displayed on the vehicle', 'conditional', 'operations', 0, 0,
 'Kept legible', 'Self-propelled commercial motor vehicle in interstate commerce',
 'The carrier''s legal name and USDOT number on both sides, legible from 50 feet.',
 '49 CFR 390.21', 'FMCSA', CONCAT(@ecfr, '49/section-390.21'), 70),
-- Federal, recommended ---------------------------------------------------------------------------
('c0666666-0000-4000-8000-000000000008', 'US', 'vehicle', 'VEHICLE_INSURANCE_CARD', 'Insurance identification card in the vehicle', 'recommended', 'insurance', 1, 0,
 'Policy term', '', 'Proof of coverage carried in the vehicle; States and brokers expect it even where federal law is silent.',
 NULL, 'State law and broker contracts', NULL, 310),
('c0666666-0000-4000-8000-000000000009', 'US', 'vehicle', 'LIFT_LOAD_TEST', 'Wheelchair lift load test and certification', 'recommended', 'inspection', 1, 0,
 'Per the manufacturer; yearly is common', 'Vehicle carries a lift',
 'Not a federal requirement, but manufacturers, insurers and broker contracts routinely ask for it.',
 NULL, 'Manufacturers and broker contracts', NULL, 320),
('c0666666-0000-4000-8000-000000000010', 'US', 'vehicle', 'DAILY_INSPECTION_LOG', 'Daily pre-trip and post-trip inspection log', 'recommended', 'inspection', 0, 0,
 'Each day the vehicle is used', 'Vehicle is below the commercial line',
 'The habit part 396 imposes on commercial vehicles, kept voluntarily on vans; brokers often require it.',
 NULL, 'Broker contracts and good practice', NULL, 330),
-- Florida ------------------------------------------------------------------------------------------
('c0666666-0000-4000-8000-000000000011', 'FL', 'vehicle', 'FL_REGISTRATION', 'Florida vehicle registration', 'required', 'operations', 1, 0,
 'Yearly, on the owner''s renewal date', '', 'Every vehicle driven on Florida roads must be registered with the State.',
 'F.S. 320.02(1)', 'Florida DHSMV', CONCAT(@fs, '320.02'), 10),
('c0666666-0000-4000-8000-000000000012', 'FL', 'vehicle', 'FL_BUS_SAFETY_INSPECTION', 'Annual bus safety inspection', 'conditional', 'inspection', 1, 0,
 'At least annually', 'Operates under a Community Transportation Coordinator''s coordinated system',
 'Inspected by someone with at least a year as a mechanic or inspector who can identify defective components. It reaches vans in the coordinated system, not only commercial vehicles.',
 'F.A.C. 14-90.009', 'FDOT', CONCAT(@fac, '14-90.009'), 20),
('c0666666-0000-4000-8000-000000000013', 'FL', 'vehicle', 'FL_EQUIPMENT_STANDARDS', 'Vehicle equipment and procurement record', 'conditional', 'inspection', 0, 0,
 'At purchase, then as equipment changes', 'Operates under a Community Transportation Coordinator''s coordinated system',
 'The bus must meet the listed Federal Motor Vehicle Safety Standards and Florida''s equipment rules - mirrors, signage and the rest - and new buses need proof of strength and structural integrity tests.',
 'F.A.C. 14-90.007', 'FDOT', CONCAT(@fac, '14-90.007'), 30);
