-- ################################################################################################
-- # 025 - Florida (jurisdiction 'FL'): what Florida law adds on top of the federal layer.
-- #
-- # Only what Florida itself demands. Nothing here repeats a federal row: enrollment, exclusion
-- # screening, NPI, HIPAA and the FMCSA items stay in the 'US' layer and apply everywhere. Where
-- # Florida tightens a federal item (insurance limits, a fixed retention period, its own screening),
-- # the row says what Florida adds.
-- #
-- # Every citation checked against the Florida Statutes text on 2026-09-22 (flsenate.gov).
-- # Not covered here: county and city rules (vehicle-for-hire permits), which are a separate layer,
-- # and the broker contracts, which are not law.
-- ################################################################################################
SET @fs = 'https://www.flsenate.gov/Laws/Statutes/2024/';

INSERT IGNORE INTO compliancedocs
    (recordid, jurisdiction, subject, code, name, obligation, category, expires, driversign, renewal, appliesif,
     description, legalcitation, authority, sourceurl, sortorder)
VALUES
-- Required ---------------------------------------------------------------------------------------
('c0222222-0000-4000-8000-000000000001', 'FL', 'company', 'FL_L2_SCREENING', 'Level 2 background screening through AHCA', 'required', 'enrollment', 1, 0,
 'Fingerprints are retained on a 5-year renewal basis', 'Enrolled as a Florida Medicaid provider',
 'Screening of the provider and each principal - officers, directors, billing agents, managing employees and anyone holding 5% or more.',
 'F.S. 409.907(8); F.S. 435.12', 'AHCA', CONCAT(@fs, '409.907'), 10),
('c0222222-0000-4000-8000-000000000002', 'FL', 'company', 'FL_MEDICAID_RECORDS', 'Medicaid records kept for 6 years', 'required', 'enrollment', 0, 0,
 'Keep 6 years, and deliver on request to AHCA or the Attorney General''s Medicaid Fraud Control Unit',
 'Enrolled as a Florida Medicaid provider',
 'Florida''s provider agreement fixes the retention period that federal law leaves open.',
 'F.S. 409.907(3)', 'AHCA', CONCAT(@fs, '409.907'), 20),
('c0222222-0000-4000-8000-000000000003', 'FL', 'company', 'FL_FORHIRE_INSURANCE', 'For-hire auto liability at Florida limits ($125k/$250k/$50k)', 'required', 'insurance', 1, 0,
 'Policy term', 'Operates for-hire passenger vehicles in Florida',
 'Florida sets the limits federal law does not: $125,000 per person, $250,000 per incident, $50,000 property damage.',
 'F.S. 324.032(1)(a)', 'Florida DHSMV', CONCAT(@fs, '324.032'), 30),
('c0222222-0000-4000-8000-000000000004', 'FL', 'company', 'FL_ANNUAL_REPORT', 'Florida annual report (Division of Corporations)', 'required', 'operations', 1, 0,
 'Yearly, between January 1 and May 1', 'Registered with the Florida Division of Corporations',
 'Keeps the company active on Sunbiz; late filing brings a penalty and, eventually, administrative dissolution.',
 'F.S. 605.0212 (LLC); F.S. 607.1622 (corporation)', 'Florida Department of State', CONCAT(@fs, '605.0212'), 40),
-- Required if ------------------------------------------------------------------------------------
('c0222222-0000-4000-8000-000000000005', 'FL', 'company', 'FL_WORKERS_COMP', 'Florida workers'' compensation coverage', 'conditional', 'insurance', 1, 0,
 'Policy term', 'Four or more employees (outside construction)',
 'Florida requires coverage at four employees; the federal layer only listed it as good practice.',
 'F.S. 440.02(17)(b)', 'Florida Division of Workers'' Compensation', CONCAT(@fs, '440.02'), 50),
('c0222222-0000-4000-8000-000000000006', 'FL', 'company', 'FL_FICTITIOUS_NAME', 'Fictitious name registration', 'conditional', 'operations', 1, 0,
 'Every 5 years, expiring December 31 of the fifth year', 'Operates under a name other than the registered legal name',
 'Registered with the Division of Corporations under the Fictitious Name Act.',
 'F.S. 865.09', 'Florida Department of State', CONCAT(@fs, '865.09'), 60),
('c0222222-0000-4000-8000-000000000007', 'FL', 'company', 'FL_BUSINESS_TAX_RECEIPT', 'Local business tax receipt', 'conditional', 'operations', 1, 0,
 'Yearly; receipts expire September 30', 'The county or municipality levies the tax',
 'Counties and cities may levy a business tax; the receipt is proof it was paid where they do.',
 'F.S. 205.053', 'County or municipality', CONCAT(@fs, '205.053'), 70),
('c0222222-0000-4000-8000-000000000008', 'FL', 'company', 'FL_CTC_CONTRACT', 'Transportation Disadvantaged operator contract', 'conditional', 'operations', 1, 0,
 'Reviewed annually by the coordinator', 'Carries Transportation Disadvantaged trips in a county''s coordinated system',
 'The Community Transportation Coordinator contracts with operators on a standard contract carrying performance standards.',
 'F.S. 427.0155(1)', 'Commission for the Transportation Disadvantaged', CONCAT(@fs, '427.0155'), 80),
('c0222222-0000-4000-8000-000000000009', 'FL', 'company', 'FL_INTRASTATE_FMCSR', 'Intrastate FMCSA safety records (49 CFR 382-386, 390-397)', 'conditional', 'safety', 0, 0,
 'Retention varies by record type', 'Vehicles of 10,000 lb GVWR or more, or designed for more than 15 passengers including the driver',
 'Florida applies the federal motor carrier rules to intrastate operation too, as they stood on December 31, 2023, with Florida''s own hours-of-service limits.',
 'F.S. 316.302(1)(b); F.S. 316.003', 'Florida Highway Patrol', CONCAT(@fs, '316.302'), 90),
-- Recommended ------------------------------------------------------------------------------------
('c0222222-0000-4000-8000-000000000010', 'FL', 'company', 'FL_DRUG_FREE_WORKPLACE', 'Drug-free workplace program', 'recommended', 'employment', 0, 0,
 'Review yearly', 'Wants the workers'' compensation premium credit',
 'Voluntary in Florida: a qualifying program earns a premium credit and affects benefit eligibility after a positive test.',
 'F.S. 440.102', 'Florida Division of Workers'' Compensation', CONCAT(@fs, '440.102'), 100);
