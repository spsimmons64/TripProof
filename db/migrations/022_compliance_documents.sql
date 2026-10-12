-- ################################################################################################
-- # 022 - company compliance documents: the paperwork an NEMT company needs to operate, apart from
-- # the per-trip credential checks.
-- #
-- # obligation  'required'    the law requires it (the citation says which)
-- #             'recommended' not federal law, but expected by brokers, insurers or good practice
-- # expires     whether the document carries a renewal or refresh date (renewal says how often)
-- # driversign  each driver signs it, and the company keeps the signed copy in the driver's file
-- # appliesif   the condition that brings it into play, in plain words ('' = everyone)
-- #
-- # Seeded with the federal layer (jurisdiction 'US'), every citation checked against the current
-- # statute/eCFR text on 2026-09-22. States come later, as more rows with their own jurisdiction.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS compliancedocs (
    recordid       VARCHAR(36)   NOT NULL,
    jurisdiction   VARCHAR(8)    NOT NULL DEFAULT 'US',       -- 'US' today; a state code later
    code           VARCHAR(48)   NOT NULL,
    name           VARCHAR(160)  NOT NULL,
    obligation     VARCHAR(12)   NOT NULL,                    -- required | recommended
    category       VARCHAR(16)   NULL,                        -- enrollment | privacy | employment | safety | insurance | operations
    expires        TINYINT(1)    NOT NULL DEFAULT 0,
    driversign     TINYINT(1)    NOT NULL DEFAULT 0,
    renewal        VARCHAR(80)   NULL,                        -- how often, when it expires or must be refreshed
    appliesif      VARCHAR(255)  NULL,
    description    VARCHAR(512)  NULL,
    legalcitation  VARCHAR(128)  NULL,
    authority      VARCHAR(96)   NULL,
    sourceurl      VARCHAR(512)  NULL,
    sortorder      INT           NOT NULL DEFAULT 0,
    active         TINYINT(1)    NOT NULL DEFAULT 1,
    added          DATETIME      NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated        DATETIME      NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_compliancedocs_code (jurisdiction, code),
    CONSTRAINT ck_compliancedocs_obligation CHECK (obligation IN ('required', 'recommended'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @ecfr = 'https://www.ecfr.gov/current/title-';

INSERT IGNORE INTO compliancedocs
    (recordid, jurisdiction, code, name, obligation, category, expires, driversign, renewal, appliesif, description,
     legalcitation, authority, sourceurl, sortorder)
VALUES
-- Required ---------------------------------------------------------------------------------------
('c0111111-0000-4000-8000-000000000001', 'US', 'NPI', 'National Provider Identifier (NPI)', 'required', 'enrollment', 0, 0, NULL,
 'Bills health care claims electronically', 'Obtained from NPPES and used on claims.',
 '45 CFR 162.410', 'HHS (HIPAA)', CONCAT(@ecfr, '45/section-162.410'), 10),
('c0111111-0000-4000-8000-000000000002', 'US', 'MEDICAID_ENROLLMENT', 'State Medicaid enrollment and revalidation', 'required', 'enrollment', 1, 0, 'At least every 5 years',
 'Bills Medicaid, directly or through a broker network', 'Screened and enrolled with the State Medicaid agency; network providers of managed care plans must be enrolled too.',
 '42 CFR 455.414; 42 CFR 438.602(b)(1)', 'CMS', CONCAT(@ecfr, '42/section-455.414'), 20),
('c0111111-0000-4000-8000-000000000003', 'US', 'OWNERSHIP_DISCLOSURE', 'Ownership and control disclosure', 'required', 'enrollment', 0, 0, 'At enrollment, at revalidation and within 35 days of a change',
 'Enrolled as a Medicaid provider', 'Owners with 5% or more, managing employees, related business interests and any prior sanctions.',
 '42 CFR 455.104', 'CMS', CONCAT(@ecfr, '42/section-455.104'), 30),
('c0111111-0000-4000-8000-000000000004', 'US', 'EXCLUSION_SCREENING', 'Exclusion screening records (OIG LEIE and SAM.gov)', 'required', 'enrollment', 1, 0, 'Monthly',
 'Bills a Federal health care program', 'No payment may be made for anything furnished by an excluded person; monthly screening of staff and contractors is the OIG''s stated expectation.',
 '42 U.S.C. 1396a(a)(87)(A); 42 CFR 1001.1901', 'Congress; HHS-OIG', 'https://oig.hhs.gov/exclusions/', 40),
('c0111111-0000-4000-8000-000000000005', 'US', 'RECORD_RETENTION', 'Record retention and disclosure agreement', 'required', 'enrollment', 0, 0, NULL,
 'Enrolled as a Medicaid provider', 'Keep records that fully disclose the services billed and furnish them to the State and HHS on request.',
 '42 CFR 431.107(b)', 'CMS', CONCAT(@ecfr, '42/section-431.107'), 50),
('c0111111-0000-4000-8000-000000000006', 'US', 'DRUG_LAW_PROCESS', 'Written process for State drug-law violations', 'required', 'employment', 0, 0, NULL, '',
 'A documented process for addressing a driver''s violation of a State drug law.',
 '42 U.S.C. 1396a(a)(87)(C)', 'Congress (CAA 2021 §209)', 'https://www.govinfo.gov/link/uscode/42/1396a', 60),
('c0111111-0000-4000-8000-000000000007', 'US', 'DRIVING_HISTORY_PROCESS', 'Written process for disclosing driving history', 'required', 'employment', 0, 0, NULL, '',
 'A documented process for disclosing each driver''s driving history, including traffic violations, to the State Medicaid program.',
 '42 U.S.C. 1396a(a)(87)(D)', 'Congress (CAA 2021 §209)', 'https://www.govinfo.gov/link/uscode/42/1396a', 70),
('c0111111-0000-4000-8000-000000000008', 'US', 'EIN', 'Employer Identification Number (IRS)', 'required', 'operations', 0, 0, NULL, '',
 'The federal tax identification number the business files and reports under.',
 '26 CFR 301.6109-1', 'IRS', 'https://www.irs.gov/businesses/small-businesses-self-employed/employer-id-numbers', 80),
('c0111111-0000-4000-8000-000000000009', 'US', 'I9', 'Form I-9 for every employee', 'required', 'employment', 0, 1, 'Keep 3 years after hire or 1 year after separation, whichever is later',
 '', 'Employment eligibility verification, retained and produced on inspection.',
 '8 CFR 274a.2', 'DHS / USCIS', CONCAT(@ecfr, '8/section-274a.2'), 90),
('c0111111-0000-4000-8000-000000000010', 'US', 'HIPAA_RISK_ANALYSIS', 'HIPAA security risk analysis', 'required', 'privacy', 0, 0, 'Review periodically and after any material change',
 'Handles protected health information', 'An assessment of risks to electronic PHI, with the risk management steps taken.',
 '45 CFR 164.308(a)(1)(ii)(A)', 'HHS (HIPAA)', CONCAT(@ecfr, '45/section-164.308'), 100),
('c0111111-0000-4000-8000-000000000011', 'US', 'HIPAA_POLICIES', 'HIPAA privacy and security policies', 'required', 'privacy', 0, 0, 'Keep 6 years from creation or last effective date',
 'Handles protected health information', 'Written policies and procedures, plus the notice of privacy practices.',
 '45 CFR 164.316; 45 CFR 164.520', 'HHS (HIPAA)', CONCAT(@ecfr, '45/section-164.316'), 110),
('c0111111-0000-4000-8000-000000000012', 'US', 'HIPAA_BAA', 'Business associate agreements', 'required', 'privacy', 0, 0, 'On signing and when a vendor changes',
 'Vendors handle PHI (dispatch, scheduling, billing)', 'A signed agreement with every vendor that creates, receives, maintains or transmits PHI.',
 '45 CFR 164.308(b)(1); 45 CFR 164.502(e)', 'HHS (HIPAA)', CONCAT(@ecfr, '45/section-164.502'), 120),
('c0111111-0000-4000-8000-000000000013', 'US', 'HIPAA_TRAINING', 'Security awareness and training records', 'required', 'privacy', 1, 0, 'Periodic; annual is the common practice',
 'Handles protected health information', 'Records that workforce members were trained and given periodic security reminders.',
 '45 CFR 164.308(a)(5)', 'HHS (HIPAA)', CONCAT(@ecfr, '45/section-164.308'), 130),
('c0111111-0000-4000-8000-000000000014', 'US', 'USDOT_MCS150', 'USDOT number and MCS-150 update', 'required', 'operations', 1, 0, 'Every 24 months',
 'Interstate operation, or vehicles designed for 9 or more passengers for direct compensation', 'Registration with FMCSA, kept current by the biennial update.',
 '49 CFR 390.19; 49 CFR 390.21', 'FMCSA', CONCAT(@ecfr, '49/section-390.19'), 140),
('c0111111-0000-4000-8000-000000000015', 'US', 'DA_TESTING_PROGRAM', 'Drug and alcohol testing program records', 'required', 'employment', 0, 0, 'Retention varies by record type',
 'CDL drivers operating commercial motor vehicles', 'Policy, testing records, supervisor training and the designated employer representative.',
 '49 CFR part 382', 'FMCSA', CONCAT(@ecfr, '49/part-382'), 150),
('c0111111-0000-4000-8000-000000000016', 'US', 'CLEARINGHOUSE', 'FMCSA Drug and Alcohol Clearinghouse queries', 'required', 'employment', 1, 0, 'Annually for every CDL driver',
 'CDL drivers operating commercial motor vehicles', 'Pre-employment full queries and an annual query for each driver.',
 '49 CFR 382.701(b)', 'FMCSA', CONCAT(@ecfr, '49/section-382.701'), 160),
('c0111111-0000-4000-8000-000000000017', 'US', 'BBP_PLAN', 'Bloodborne pathogens exposure control plan', 'required', 'safety', 1, 0, 'Review and update at least annually',
 'Staff can reasonably be expected to contact blood or other potentially infectious material', 'A written exposure control plan, with the annual review documented.',
 '29 CFR 1910.1030(c)', 'OSHA', CONCAT(@ecfr, '29/section-1910.1030'), 170),
('c0111111-0000-4000-8000-000000000018', 'US', 'OSHA_300', 'OSHA injury and illness records (300, 300A, 301)', 'required', 'safety', 1, 0, 'Yearly; post the 300A summary February 1 - April 30',
 'More than 10 employees and not in a partially exempt industry', 'The injury and illness log, annual summary and incident reports.',
 '29 CFR part 1904', 'OSHA', CONCAT(@ecfr, '29/part-1904'), 180),
('c0111111-0000-4000-8000-000000000019', 'US', 'FCRA_FORMS', 'FCRA disclosure and authorization forms', 'required', 'employment', 0, 1, NULL,
 'Background checks are run through a consumer reporting agency', 'A stand-alone disclosure, written authorization, and the pre-adverse and adverse action notices.',
 '15 U.S.C. 1681b(b)', 'FTC / CFPB', 'https://www.govinfo.gov/link/uscode/15/1681b', 190),
-- Recommended ------------------------------------------------------------------------------------
('c0111111-0000-4000-8000-000000000101', 'US', 'AUTO_LIABILITY_COI', 'Commercial auto liability certificate', 'recommended', 'insurance', 1, 0, 'Policy term',
 '', 'Brokers and States set the limits; federal law does not.', NULL, 'Broker and State contracts', NULL, 300),
('c0111111-0000-4000-8000-000000000102', 'US', 'GENERAL_LIABILITY_COI', 'General liability certificate', 'recommended', 'insurance', 1, 0, 'Policy term', '',
 'Commonly required by broker contracts.', NULL, 'Broker and State contracts', NULL, 310),
('c0111111-0000-4000-8000-000000000103', 'US', 'ABUSE_MOLESTATION_COI', 'Abuse and molestation coverage', 'recommended', 'insurance', 1, 0, 'Policy term', '',
 'Often demanded when transporting vulnerable passengers.', NULL, 'Broker contracts', NULL, 320),
('c0111111-0000-4000-8000-000000000104', 'US', 'HNOA_COI', 'Hired and non-owned auto coverage', 'recommended', 'insurance', 1, 0, 'Policy term',
 'Drivers use their own or rented vehicles', 'Covers vehicles the company does not own.', NULL, 'Broker contracts', NULL, 330),
('c0111111-0000-4000-8000-000000000105', 'US', 'WORKERS_COMP_COI', 'Workers'' compensation certificate', 'recommended', 'insurance', 1, 0, 'Policy term',
 'Has employees', 'Required by most States rather than by federal law; the State layer will say which.', NULL, 'State law', NULL, 340),
('c0111111-0000-4000-8000-000000000106', 'US', 'SAM_REGISTRATION', 'SAM.gov registration', 'recommended', 'enrollment', 1, 0, 'Yearly',
 'Seeks federal contracts or grants', 'Required only to hold federal awards; useful for exclusion screening either way.', NULL, 'GSA', 'https://sam.gov/', 350),
('c0111111-0000-4000-8000-000000000107', 'US', 'VEHICLE_MAINTENANCE', 'Preventive maintenance and inspection records', 'recommended', 'safety', 0, 0, 'Per maintenance schedule',
 '', 'Service history per vehicle; expected in broker and State audits.', NULL, 'Broker and State contracts', NULL, 360),
('c0111111-0000-4000-8000-000000000108', 'US', 'DRIVER_QUALIFICATION_POLICY', 'Driver qualification and hiring policy', 'recommended', 'employment', 0, 0, NULL, '',
 'What the company checks before a driver carries passengers, and how often it rechecks.', NULL, 'Good practice', NULL, 370),
('c0111111-0000-4000-8000-000000000109', 'US', 'SAFETY_PROGRAM', 'Written safety program and accident procedures', 'recommended', 'safety', 0, 0, 'Review yearly', '',
 'Accident reporting, passenger handling and incident investigation.', NULL, 'Good practice', NULL, 380),
('c0111111-0000-4000-8000-000000000110', 'US', 'EMERGENCY_PLAN', 'Emergency preparedness and continuity plan', 'recommended', 'operations', 0, 0, 'Review yearly', '',
 'How service continues through storms, outages and other disruptions.', NULL, 'Good practice', NULL, 390),
('c0111111-0000-4000-8000-000000000111', 'US', 'ACCREDITATION', 'NEMT accreditation', 'recommended', 'operations', 1, 0, 'Per accrediting body',
 '', 'Some brokers and States prefer or reward accredited providers.', NULL, 'Accrediting bodies', NULL, 400),
-- Policies each driver signs ----------------------------------------------------------------------
('c0111111-0000-4000-8000-000000000201', 'US', 'DA_POLICY_RECEIPT', 'Drug and alcohol policy - signed certificate of receipt', 'required', 'employment', 0, 1,
 'On hire and whenever the policy changes', 'CDL drivers operating commercial motor vehicles',
 'The employer must give each driver the policy and educational materials and keep the driver''s signed certificate of receipt.',
 '49 CFR 382.601(d)', 'FMCSA', CONCAT(@ecfr, '49/section-382.601'), 200),
('c0111111-0000-4000-8000-000000000202', 'US', 'CLEARINGHOUSE_CONSENT', 'Clearinghouse query consent - signed by the driver', 'required', 'employment', 0, 1,
 'Before each query; limited-query consent may cover more than one year', 'CDL drivers operating commercial motor vehicles',
 'A driver must consent before the employer queries the Clearinghouse.',
 '49 CFR 382.701(b)(2)', 'FMCSA', CONCAT(@ecfr, '49/section-382.701'), 210),
('c0111111-0000-4000-8000-000000000203', 'US', 'PHI_CONFIDENTIALITY', 'Confidentiality agreement (PHI) - signed by the driver', 'recommended', 'privacy', 0, 1,
 'On hire', 'Drivers see passenger names, addresses and destinations',
 'Backs up the HIPAA sanction policy with each driver''s written acknowledgement.',
 '45 CFR 164.308(a)(1)(ii)(C)', 'HHS (HIPAA)', CONCAT(@ecfr, '45/section-164.308'), 410),
('c0111111-0000-4000-8000-000000000204', 'US', 'MVR_RELEASE', 'Driving record release - signed by the driver', 'recommended', 'employment', 0, 1,
 'On hire and before each recheck', '', 'Written permission to pull the driver''s motor vehicle record.',
 NULL, 'State DMV rules', NULL, 420),
('c0111111-0000-4000-8000-000000000205', 'US', 'HANDBOOK_ACK', 'Driver handbook acknowledgement', 'recommended', 'employment', 0, 1,
 'On hire and at each revision', '', 'Conduct, attendance, uniform, passenger service and discipline rules.',
 NULL, 'Good practice', NULL, 430),
('c0111111-0000-4000-8000-000000000206', 'US', 'VEHICLE_USE_ACK', 'Vehicle use and accident reporting policy acknowledgement', 'recommended', 'safety', 0, 1,
 'On hire and at each revision', '', 'Personal use, inspections, fueling, and what to do after an incident.',
 NULL, 'Good practice', NULL, 440),
('c0111111-0000-4000-8000-000000000207', 'US', 'DISTRACTED_DRIVING_ACK', 'Mobile phone and distracted driving policy acknowledgement', 'recommended', 'safety', 0, 1,
 'On hire and at each revision', '', 'Hand-held phone use and texting are barred outright for CMV drivers; most companies apply the rule to every driver.',
 '49 CFR 392.80; 49 CFR 392.82', 'FMCSA', CONCAT(@ecfr, '49/section-392.82'), 450),
('c0111111-0000-4000-8000-000000000208', 'US', 'PASSENGER_SERVICE_ACK', 'Passenger assistance and ADA service policy acknowledgement', 'recommended', 'safety', 0, 1,
 'On hire and at each revision', '', 'Securement, assistance, service animals and refusal-of-service rules.',
 '49 CFR 37.173', 'U.S. DOT (ADA)', CONCAT(@ecfr, '49/section-37.173'), 460);
