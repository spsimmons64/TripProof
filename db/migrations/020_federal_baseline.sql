-- ################################################################################################
-- # 020 - the federal baseline for NEMT transport companies (not brokers).
-- #
-- # One published rule set, US-FED v1 (level federal, state 'US'), checked on every trip:
-- #   driver   valid license, not excluded (OIG LEIE), driving history on file, ADA passenger training,
-- #            wheelchair securement training (wheelchair trips)
-- #   vehicle  wheelchair lift in operative condition (wheelchair trips)
-- #   company  drug-law violation process, NPI, State Medicaid enrollment, HIPAA risk analysis
-- # plus obligations (kind 'obligation'): duties with nothing to prove per trip, kept on each
-- # customer's checklist (accountchecklist) instead.
-- #
-- # Every citation was checked against the current text (govinfo 42 U.S.C. 1396a; eCFR) on
-- # 2026-09-21. Where federal law sets no refresh interval, the requirement has no age limit
-- # (noagelimit) rather than borrowing a state or broker's.
-- ################################################################################################
INSERT INTO credentialtypes (recordid, code, name, subject, category, description)
SELECT '9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0001', 'DRUG_LAW_POLICY', 'Drug-law violation policy', 'company', 'policy',
       'Written process for addressing a driver''s violation of a State drug law'
WHERE NOT EXISTS (SELECT 1 FROM credentialtypes WHERE code = 'DRUG_LAW_POLICY');

UPDATE credentialtypes SET name = 'State Medicaid enrollment' WHERE code = 'MEDICAID_ENROLLMENT';

INSERT INTO rulesets (recordid, family, state, level, version, name, effectivefrom, source, verified, status, publishedon)
SELECT '9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0100', 'US-FED', 'US', 'federal', 1, 'Federal baseline', '2020-12-27',
       'U.S.C. and CFR, checked 2026-09-21', 1, 'published', UTC_TIMESTAMP()
WHERE NOT EXISTS (SELECT 1 FROM rulesets WHERE family = 'US-FED' AND version = 1);

SET @rs = '9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0100';
SET @usc87 = 'https://www.govinfo.gov/link/uscode/42/1396a';

INSERT IGNORE INTO requirements
    (recordid, rulesetid, code, kind, status, subject, category, credentialtypeid, noagelimit, servicelevels,
     description, legalcitation, sourcetype, authorityname, sourceurl, quote)
VALUES
-- Checked on every trip ---------------------------------------------------------------------------
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0101', @rs, 'FED-DRIVER-LICENSE', 'credential', 'REQUIRED', 'driver', 'licensing',
 (SELECT recordid FROM credentialtypes WHERE code = 'DRIVER_LICENSE'), 0, NULL,
 'Driver holds a valid driver''s license', '42 U.S.C. 1396a(a)(87)(B)', 'PRIMARY_STATUTE', 'Congress (CAA 2021 §209)', @usc87,
 'each such individual driver has a valid driver''s license'),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0102', @rs, 'FED-EXCLUSION', 'credential', 'REQUIRED', 'driver', 'screening',
 (SELECT recordid FROM credentialtypes WHERE code = 'OIG_EXCLUSION'), 0, NULL,
 'Driver is not on the OIG exclusion list (monthly check)', '42 U.S.C. 1396a(a)(87)(A); 42 CFR 1001.1901', 'PRIMARY_STATUTE', 'Congress (CAA 2021 §209); HHS-OIG', @usc87,
 'each such provider and individual driver is not excluded from participation in any Federal health care program … and is not listed on the exclusion list of the Inspector General'),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0103', @rs, 'FED-DRIVING-HISTORY', 'credential', 'REQUIRED', 'driver', 'screening',
 (SELECT recordid FROM credentialtypes WHERE code = 'MVR'), 1, NULL,
 'Driving history on file for disclosure to the State Medicaid program', '42 U.S.C. 1396a(a)(87)(D)', 'PRIMARY_STATUTE', 'Congress (CAA 2021 §209)', @usc87,
 'each such provider has in place a process to disclose to the State Medicaid program the driving history, including any traffic violations, of each such individual driver'),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0104', @rs, 'FED-ADA-TRAINING', 'credential', 'REQUIRED', 'driver', 'training',
 (SELECT recordid FROM credentialtypes WHERE code = 'PASSENGER_ASSIST'), 0, NULL,
 'Driver trained to assist riders with disabilities', '49 CFR 37.173', 'PRIMARY_REGULATION', 'U.S. DOT (ADA)', 'https://www.ecfr.gov/current/title-49/section-37.173',
 'personnel are trained to proficiency, as appropriate to their duties, so that they operate vehicles and equipment safely and properly assist and treat individuals with disabilities'),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0105', @rs, 'FED-SECUREMENT-TRAINING', 'credential', 'REQUIRED', 'driver', 'training',
 (SELECT recordid FROM credentialtypes WHERE code = 'WHEELCHAIR_SECUREMENT'), 0, '["wheelchair"]',
 'Driver trained on wheelchair lift and securement equipment', '49 CFR 37.173', 'PRIMARY_REGULATION', 'U.S. DOT (ADA)', 'https://www.ecfr.gov/current/title-49/section-37.173',
 'personnel are trained to proficiency … so that they operate vehicles and equipment safely'),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0106', @rs, 'FED-LIFT-OPERATIVE', 'credential', 'REQUIRED', 'vehicle', 'inspection',
 (SELECT recordid FROM credentialtypes WHERE code = 'LIFT_CERTIFICATION'), 0, '["wheelchair"]',
 'Wheelchair lift certified in operative condition', '49 CFR 37.161', 'PRIMARY_REGULATION', 'U.S. DOT (ADA)', 'https://www.ecfr.gov/current/title-49/section-37.161',
 'Public and private entities providing transportation services shall maintain in operative condition those features … including … lifts and other means of access to vehicles, securement devices'),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0107', @rs, 'FED-DRUG-LAW-PROCESS', 'credential', 'REQUIRED', 'company', 'policy',
 (SELECT recordid FROM credentialtypes WHERE code = 'DRUG_LAW_POLICY'), 0, NULL,
 'Written process for addressing State drug-law violations', '42 U.S.C. 1396a(a)(87)(C)', 'PRIMARY_STATUTE', 'Congress (CAA 2021 §209)', @usc87,
 'each such provider has in place a process to address any violation of a State drug law'),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0108', @rs, 'FED-NPI', 'credential', 'REQUIRED', 'company', 'enrollment',
 (SELECT recordid FROM credentialtypes WHERE code = 'NPI_REGISTRATION'), 0, NULL,
 'Company has its own NPI', '45 CFR 162.410(a)(1)', 'PRIMARY_REGULATION', 'HHS (HIPAA)', 'https://www.ecfr.gov/current/title-45/section-162.410',
 'A covered entity that is a covered health care provider must: (1) Obtain … an NPI from the National Provider System (NPS) for itself'),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0109', @rs, 'FED-MEDICAID-ENROLLMENT', 'credential', 'REQUIRED', 'company', 'enrollment',
 (SELECT recordid FROM credentialtypes WHERE code = 'MEDICAID_ENROLLMENT'), 0, NULL,
 'Company screened and enrolled with the State Medicaid agency', '42 CFR 438.602(b)(1); 42 CFR 455.410(a)', 'PRIMARY_REGULATION', 'CMS', 'https://www.ecfr.gov/current/title-42/section-438.602',
 'The State must screen and enroll, and periodically revalidate, all network providers of MCOs, PIHPs, and PAHPs'),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0110', @rs, 'FED-HIPAA-RISK', 'credential', 'REQUIRED', 'company', 'privacy',
 (SELECT recordid FROM credentialtypes WHERE code = 'HIPAA_RISK_ANALYSIS'), 1, NULL,
 'HIPAA security risk analysis on file', '45 CFR 164.308(a)(1)(ii)(A)', 'PRIMARY_REGULATION', 'HHS (HIPAA)', 'https://www.ecfr.gov/current/title-45/section-164.308',
 'Conduct an accurate and thorough assessment of the potential risks and vulnerabilities to the confidentiality, integrity, and availability of electronic protected health information'),
-- Checklist (not checked per trip) ----------------------------------------------------------------
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0201', @rs, 'FED-OWNERSHIP-DISCLOSURE', 'obligation', 'REQUIRED', 'company', 'enrollment', NULL, 0, NULL,
 'Disclose owners (5% or more), managing employees and related parties to the State Medicaid agency', '42 CFR 455.104', 'PRIMARY_REGULATION', 'CMS', 'https://www.ecfr.gov/current/title-42/section-455.104', NULL),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0202', @rs, 'FED-SITE-INSPECTIONS', 'obligation', 'REQUIRED', 'company', 'enrollment', NULL, 0, NULL,
 'Permit unannounced on-site inspections by CMS, its contractors or the State Medicaid agency', '42 CFR 455.432(b)', 'PRIMARY_REGULATION', 'CMS', 'https://www.ecfr.gov/current/title-42/section-455.432',
 'Must require any enrolled provider to permit CMS, its agents, its designated contractors, or the State Medicaid agency to conduct unannounced on-site inspections'),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0203', @rs, 'FED-OWNER-FINGERPRINTS', 'obligation', 'CONDITIONAL', 'company', 'enrollment', NULL, 0, NULL,
 'If the State rates you high risk: criminal background check and fingerprints for each 5%+ owner', '42 CFR 455.434', 'PRIMARY_REGULATION', 'CMS', 'https://www.ecfr.gov/current/title-42/section-455.434', NULL),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0204', @rs, 'FED-ACCESSIBILITY-UPKEEP', 'obligation', 'REQUIRED', 'company', 'vehicle', NULL, 0, NULL,
 'Keep lifts, ramps and securement devices working; repair promptly and accommodate riders while out of order', '49 CFR 37.161', 'PRIMARY_REGULATION', 'U.S. DOT (ADA)', 'https://www.ecfr.gov/current/title-49/section-37.161',
 'Accessibility features shall be repaired promptly if they are damaged or out of order'),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0205', @rs, 'FED-VEHICLE-SPECS', 'obligation', 'REQUIRED', 'company', 'vehicle', NULL, 0, NULL,
 'Accessible vehicles meet Part 38: lift rated 600 lb+ and interlocked so the vehicle can''t move unless stowed; securement area 30 × 48 in.', '49 CFR 38.23', 'PRIMARY_REGULATION', 'U.S. DOT (ADA)', 'https://www.ecfr.gov/current/title-49/section-38.23',
 'The design load of the lift shall be at least 600 pounds'),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0206', @rs, 'FED-HIPAA-BAA', 'obligation', 'REQUIRED', 'company', 'privacy', NULL, 0, NULL,
 'Business associate agreements with every vendor that handles PHI (dispatch, scheduling, billing software)', '45 CFR 164.308(b)(1)', 'PRIMARY_REGULATION', 'HHS (HIPAA)', 'https://www.ecfr.gov/current/title-45/section-164.308', NULL),
('9b0e2c1a-4f7d-4f59-9a51-2f0c3d1e0207', @rs, 'FED-HIPAA-TRAINING', 'obligation', 'REQUIRED', 'company', 'privacy', NULL, 0, NULL,
 'Security awareness and training program for all staff', '45 CFR 164.308(a)(5)', 'PRIMARY_REGULATION', 'HHS (HIPAA)', 'https://www.ecfr.gov/current/title-45/section-164.308', NULL);

-- Each customer's progress on the checklist, by requirement code (codes survive new versions).
CREATE TABLE IF NOT EXISTS accountchecklist (
    accountid    VARCHAR(36)   NOT NULL,
    code         VARCHAR(64)   NOT NULL,
    completedon  DATE          NULL,
    note         VARCHAR(512)  NULL,
    updatedby    VARCHAR(36)   NULL,
    updated      DATETIME      NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (accountid, code),
    CONSTRAINT fk_accountchecklist_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
