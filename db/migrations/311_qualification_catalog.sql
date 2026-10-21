-- ################################################################################################
-- # 311 - one qualification, many sources.
-- #
-- # A rule was both WHAT is tracked and WHY it is asked, so one thing required by two authorities
-- # showed up twice - the license under FMCSA and again under Medicaid - and had to be merged by
-- # hand. The catalog is the WHAT: one row per qualification TripProof can verify, with an ID that
-- # never changes. A rule is the WHY: it points at one qualification, and several rules may point at
-- # the same one. The driver's file shows one row per qualification, with every source behind it.
-- #
-- # The rule also says which of five authority categories it belongs to, whether failing it stops
-- # dispatch or is an HR matter, and whether anybody has reviewed it as a statement of law. Every
-- # existing rule starts as a draft: none has been signed off by a reviewer, and the file must not
-- # claim otherwise.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS qualificationcatalog (
  code        VARCHAR(16)  NOT NULL PRIMARY KEY,   -- DRV-001; permanent, never reused
  name        VARCHAR(128) NOT NULL,
  area        VARCHAR(16)  NOT NULL,               -- licensing | background | training | medical
                                                   -- | drugalcohol | employment
  subject     VARCHAR(16)  NOT NULL DEFAULT 'driver',
  description VARCHAR(512) NULL,
  sortorder   INT          NOT NULL DEFAULT 0,
  retiredon   DATE         NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE compliancerules
  ADD COLUMN IF NOT EXISTS qualificationcode VARCHAR(16) NULL AFTER code,
  -- FEDERAL_GENERAL | STATE_GENERAL | FEDERAL_MEDICAID | STATE_MEDICAID | CONTRACT_COMPANY
  ADD COLUMN IF NOT EXISTS authoritycategory VARCHAR(24) NULL AFTER authoritytype,
  -- dispatch: failing it stops the driver from trips. hr: an employment-onboarding obligation,
  -- tracked and chased but never a reason to pull a driver off the road.
  ADD COLUMN IF NOT EXISTS enforcement VARCHAR(16) NOT NULL DEFAULT 'dispatch' AFTER gate,
  -- draft | reviewed | approved | retired - whether a person has signed this off as the law.
  ADD COLUMN IF NOT EXISTS legalreview VARCHAR(12) NOT NULL DEFAULT 'draft' AFTER enforcement,
  ADD COLUMN IF NOT EXISTS legalreviewedby VARCHAR(36) NULL AFTER legalreview,
  ADD COLUMN IF NOT EXISTS legalreviewedon DATETIME NULL AFTER legalreviewedby;

INSERT IGNORE INTO qualificationcatalog (code, name, area, sortorder) VALUES
  ('DRV-001', 'Valid driver''s license', 'licensing', 10),
  ('DRV-002', 'License class and endorsements', 'licensing', 11),
  ('DRV-003', 'Motor vehicle records', 'licensing', 12),
  ('DRV-004', 'Annual inquiry and review of driving record', 'licensing', 13),
  ('DRV-005', 'Driver employment application', 'licensing', 14),
  ('DRV-006', 'Previous employer safety performance history', 'licensing', 15),
  ('DRV-007', 'Consent to release safety performance history', 'licensing', 16),
  ('DRV-008', 'Road test certificate or accepted equivalent', 'licensing', 17),
  ('DRV-009', 'Minimum age for interstate operation', 'licensing', 18),
  ('DRV-010', 'Able to read and speak English', 'licensing', 19),
  ('DRV-011', 'Previous 7 days'' on-duty hours statement', 'licensing', 20),
  ('DRV-012', 'Driver qualification file (Florida intrastate)', 'licensing', 21),
  ('BKG-001', 'OIG LEIE exclusion screening', 'background', 30),
  ('BKG-002', 'SAM.gov exclusion and debarment screening', 'background', 31),
  ('BKG-003', 'Florida Level 1 background screening', 'background', 32),
  ('BKG-004', 'Level 2 fingerprint screening', 'background', 33),
  ('BKG-005', 'Background screening', 'background', 34),
  ('BKG-008', 'Abuse registry check', 'background', 35),
  ('TRN-003', 'Passenger assistance and wheelchair securement training', 'training', 50),
  ('TRN-004', 'HIPAA privacy and security training', 'training', 51),
  ('TRN-005', 'Bloodborne pathogens training', 'training', 52),
  ('TRN-006', 'Defensive driving course', 'training', 53),
  ('TRN-011', 'Entry-level driver training verification', 'training', 54),
  ('TRN-012', 'First aid certification', 'training', 55),
  ('TRN-013', 'CPR and AED certification', 'training', 56),
  ('MED-001', 'Medical certificate', 'medical', 70),
  ('MED-002', 'Bus transit medical examination', 'medical', 71),
  ('MED-003', 'CDLIS medical certification status', 'medical', 72),
  ('MED-004', 'Skill performance evaluation certificate', 'medical', 73),
  ('DRA-001', 'Pre-employment drug test', 'drugalcohol', 80),
  ('DRA-002', 'Clearinghouse pre-employment full query', 'drugalcohol', 81),
  ('DRA-003', 'Random testing pool membership', 'drugalcohol', 82),
  ('DRA-004', 'Pre-employment drug screen (additional panels)', 'drugalcohol', 83),
  ('DRA-005', 'Drug and alcohol policy - signed receipt', 'drugalcohol', 84),
  ('DRA-007', 'Clearinghouse limited query general consent', 'drugalcohol', 85),
  ('DRA-008', 'Clearinghouse annual limited query', 'drugalcohol', 86),
  ('DRA-009', 'Pre-employment drug and alcohol questionnaire', 'drugalcohol', 87),
  ('DRA-010', 'Prior DOT pre-employment violation / return-to-duty verification', 'drugalcohol', 88),
  ('DRA-011', 'Post-accident controlled substances and alcohol test', 'drugalcohol', 89),
  ('DRA-012', 'Test owed from a random selection', 'drugalcohol', 90),
  ('DRA-013', 'Follow-up testing after return to duty', 'drugalcohol', 91),
  ('DRA-014', 'Removed from safety-sensitive functions', 'drugalcohol', 92),
  ('EMP-002', 'Form I-9', 'employment', 100),
  ('EMP-003', 'Form W-4', 'employment', 101),
  ('EMP-006', 'FCRA disclosure and authorization', 'employment', 102),
  ('EMP-007', 'License suspension reporting acknowledgement', 'employment', 103),
  ('EMP-009', 'PHI confidentiality acknowledgment', 'employment', 104);

-- Which qualification each rule proves, and the category of the authority behind it.
UPDATE compliancerules r JOIN (
  SELECT 'DRIVER_LICENSE' c, 'DRV-001' q, 'FEDERAL_GENERAL' k UNION ALL
  SELECT 'DRIVER_LICENSE_COPY', 'DRV-001', 'FEDERAL_MEDICAID' UNION ALL
  SELECT 'LICENSE_ENDORSEMENTS', 'DRV-002', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'MVR_PREEMPLOYMENT', 'DRV-003', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'MVR_ANNUAL', 'DRV-004', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'EMPLOYMENT_APPLICATION', 'DRV-005', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'SAFETY_PERFORMANCE_HISTORY', 'DRV-006', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'SAFETY_PERFORMANCE_CONSENT', 'DRV-007', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'ROAD_TEST', 'DRV-008', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'DRIVER_AGE', 'DRV-009', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'ENGLISH_PROFICIENCY', 'DRV-010', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'PREV7_ONDUTY', 'DRV-011', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'FL_INTRASTATE_FULL', 'DRV-012', 'STATE_GENERAL' UNION ALL
  SELECT 'EXCLUSION_OIG_LEIE', 'BKG-001', 'FEDERAL_MEDICAID' UNION ALL
  SELECT 'EXCLUSION_SAM_GOV', 'BKG-002', 'CONTRACT_COMPANY' UNION ALL
  SELECT 'FL_LEVEL1_DRIVER', 'BKG-003', 'STATE_MEDICAID' UNION ALL
  SELECT 'FL_LEVEL2_DRIVER', 'BKG-004', 'CONTRACT_COMPANY' UNION ALL
  SELECT 'BACKGROUND_SCREENING', 'BKG-005', 'CONTRACT_COMPANY' UNION ALL
  SELECT 'ABUSE_REGISTRY_CHECK', 'BKG-008', 'CONTRACT_COMPANY' UNION ALL
  SELECT 'SECUREMENT_TRAINING_CERT', 'TRN-003', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'HIPAA_TRAINING_DRIVER', 'TRN-004', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'BBP_TRAINING', 'TRN-005', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'DEFENSIVE_DRIVING', 'TRN-006', 'CONTRACT_COMPANY' UNION ALL
  SELECT 'ELDT', 'TRN-011', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'FIRST_AID', 'TRN-012', 'CONTRACT_COMPANY' UNION ALL
  SELECT 'CPR', 'TRN-013', 'CONTRACT_COMPANY' UNION ALL
  SELECT 'MEDICAL_CERT', 'MED-001', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'FL_TRANSIT_MEDICAL', 'MED-002', 'STATE_GENERAL' UNION ALL
  SELECT 'CDL_MEDICAL_STATUS', 'MED-003', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'SPE_CERTIFICATE', 'MED-004', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'PREEMPLOYMENT_DRUG_TEST', 'DRA-001', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'FL_INTRASTATE_382', 'DRA-001', 'STATE_GENERAL' UNION ALL
  SELECT 'FL_TD_DRUG_TESTING', 'DRA-001', 'STATE_GENERAL' UNION ALL
  SELECT 'CLEARINGHOUSE_PREEMP', 'DRA-002', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'RANDOM_TESTING_RECORDS', 'DRA-003', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'NONDOT_DRUG_SCREEN', 'DRA-004', 'CONTRACT_COMPANY' UNION ALL
  SELECT 'DA_POLICY_RECEIPT', 'DRA-005', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'CLEARINGHOUSE_CONSENT', 'DRA-007', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'CLEARINGHOUSE', 'DRA-008', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'PREEMP_DA_QUESTIONNAIRE', 'DRA-009', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'PRIOR_VIOLATION_RTD', 'DRA-010', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'POSTACCIDENT_TEST', 'DRA-011', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'RANDOM_TEST_OWED', 'DRA-012', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'FOLLOWUP_TESTING', 'DRA-013', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'DA_PROHIBITION', 'DRA-014', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'I9', 'EMP-002', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'W4', 'EMP-003', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'FCRA_FORMS', 'EMP-006', 'FEDERAL_GENERAL' UNION ALL
  SELECT 'FL_LICENSE_STATUS_NOTICE', 'EMP-007', 'STATE_GENERAL' UNION ALL
  SELECT 'PHI_CONFIDENTIALITY', 'EMP-009', 'CONTRACT_COMPANY'
) m ON m.c = r.code
SET r.qualificationcode = m.q, r.authoritycategory = m.k
WHERE r.subject = 'driver' AND r.accountid IS NULL;

-- The employment forms are HR obligations. They are chased and they go on the file, but a missing
-- W-4 is a payroll matter and an I-9 has its own federal deadlines - neither is a reason to keep a
-- qualified driver off a trip.
UPDATE compliancerules SET enforcement = 'hr'
 WHERE subject = 'driver' AND accountid IS NULL AND code IN ('I9', 'W4');
