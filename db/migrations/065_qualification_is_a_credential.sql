-- ################################################################################################
-- # 065 - one noun, two questions.
-- #
-- # A credential type is a thing a subject can hold, with a validity window. Until now the hiring
-- # catalog (compliancedocs) and the credential catalog (credentialtypes) were separate lists joined
-- # by a dictionary written by hand in the API, so filing a medical card in the hiring screen had to
-- # be copied into the credential record for the trip engine to see it, and anything new had to be
-- # entered twice.
-- #
-- # A catalog item now names the credential type it is satisfied by. Where a type was missing, it is
-- # created here. Items that are not a document a driver holds - a written process, an acknowledgement
-- # inside the application, a record the company keeps - name nothing, which is the honest answer.
-- #
-- # Rule sets gain an owner. A NULL accountid is TripProof's own published content, exactly as now;
-- # a set owned by an account is that company's own policy, generated from its qualification list, so
-- # a driver missing something the company requires fails the trips they drove.
-- ################################################################################################
ALTER TABLE compliancedocs ADD COLUMN credentialtypeid VARCHAR(36) NULL AFTER category;

ALTER TABLE rulesets
    ADD COLUMN IF NOT EXISTS accountid VARCHAR(36) NULL AFTER recordid,
    ADD CONSTRAINT fk_rulesets_account FOREIGN KEY (accountid) REFERENCES accounts (recordid);

ALTER TABLE rulesets DROP CONSTRAINT IF EXISTS ck_rulesets_level;
ALTER TABLE rulesets
    ADD CONSTRAINT ck_rulesets_level CHECK (level IN ('federal', 'state', 'county', 'city', 'program', 'account'));

-- The types the hiring file collects that the credential catalog did not have yet.
INSERT IGNORE INTO credentialtypes (recordid, code, name, subject, maxagedays, defaultvaliddays, category, description, active)
VALUES
 (UUID(), 'ROAD_TEST', 'Road test certificate or equivalent', 'driver', NULL, NULL, 'licensing',
  'The certificate of a road test, or the licence or certificate accepted in place of one', 1),
 (UUID(), 'SAFETY_PERFORMANCE', 'Previous employer safety performance history', 'driver', NULL, NULL, 'screening',
  'The investigation into the previous three years of DOT-regulated employment', 1),
 (UUID(), 'CLEARINGHOUSE_QUERY', 'FMCSA Clearinghouse query', 'driver', 365, NULL, 'screening',
  'A pre-employment full query, or an annual limited query', 1),
 (UUID(), 'PSP_REPORT', 'PSP report', 'driver', NULL, NULL, 'screening',
  'The FMCSA Pre-Employment Screening Program report', 1),
 (UUID(), 'CDLIS_REPORT', 'CDLIS driver history', 'driver', NULL, NULL, 'screening',
  'The commercial driver licence information system history', 1),
 (UUID(), 'CDL_PASSENGER', 'CDL passenger endorsement', 'driver', NULL, NULL, 'licensing',
  'The passenger endorsement carried on the driver''s commercial licence', 1),
 (UUID(), 'ADA_PROFICIENCY', 'Passenger assistance and equipment proficiency', 'driver', NULL, NULL, 'training',
  'Trained to proficiency, appropriate to duties, under 49 CFR 37.173', 1),
 (UUID(), 'TRANSIT_MEDICAL', 'Bus transit medical examination', 'driver', 730, NULL, 'licensing',
  'The Florida Chapter 14-90 medical examination, FDOT form 725-030-11', 1),
 (UUID(), 'DUTY_STATUS_RECORD', 'Duty status record', 'driver', NULL, NULL, 'safety',
  'The daily record of hours on duty and driving a covered transit system keeps', 1),
 (UUID(), 'SAFETY_TRAINING', 'Safety and operating procedures training', 'driver', NULL, NULL, 'training',
  'Training and testing before driving unsupervised, and the written procedures issued with it', 1);

-- What satisfies each catalog item.
UPDATE compliancedocs c
  JOIN credentialtypes t ON t.code = CASE c.code
    WHEN 'DRIVER_LICENSE_COPY'        THEN 'DRIVER_LICENSE'
    WHEN 'CDL_LICENSE'                THEN 'DRIVER_LICENSE'
    WHEN 'CDL_PASSENGER_ENDORSEMENT'  THEN 'CDL_PASSENGER'
    WHEN 'MVR_FILE'                   THEN 'MVR'
    WHEN 'MVR_PREEMPLOYMENT'          THEN 'MVR'
    WHEN 'MVR_ANNUAL'                 THEN 'MVR'
    WHEN 'EXCLUSION_CHECK_DRIVER'     THEN 'OIG_EXCLUSION'
    WHEN 'MEDICAL_CERT'               THEN 'DOT_MEDICAL_CARD'
    WHEN 'FL_TRANSIT_MEDICAL'         THEN 'TRANSIT_MEDICAL'
    WHEN 'FL_LEVEL2_DRIVER'           THEN 'FBI_FINGERPRINT'
    WHEN 'CRIMINAL_BACKGROUND'        THEN 'BACKGROUND_CHECK'
    WHEN 'SEX_OFFENDER_CHECK'         THEN 'SEX_OFFENDER_CHECK'
    WHEN 'ABUSE_REGISTRY_CHECK'       THEN 'ABUSE_REGISTRY_CHECK'
    WHEN 'PREEMPLOYMENT_DRUG_TEST'    THEN 'DRUG_SCREEN'
    WHEN 'DRUG_SCREEN_NONCDL'         THEN 'DRUG_SCREEN'
    WHEN 'FL_TD_DRUG_TESTING'         THEN 'DRUG_SCREEN'
    WHEN 'ROAD_TEST'                  THEN 'ROAD_TEST'
    WHEN 'SAFETY_PERFORMANCE_HISTORY' THEN 'SAFETY_PERFORMANCE'
    WHEN 'CLEARINGHOUSE_PREEMP'       THEN 'CLEARINGHOUSE_QUERY'
    WHEN 'CLEARINGHOUSE'              THEN 'CLEARINGHOUSE_QUERY'
    WHEN 'PSP_REPORT'                 THEN 'PSP_REPORT'
    WHEN 'CDLIS_CHECK'                THEN 'CDLIS_REPORT'
    WHEN 'PASS_TRAINING'              THEN 'ADA_PROFICIENCY'
    WHEN 'SECUREMENT_TRAINING_CERT'   THEN 'WHEELCHAIR_SECUREMENT'
    WHEN 'BBP_TRAINING'               THEN 'BLOODBORNE_PATHOGENS'
    WHEN 'HIPAA_TRAINING_DRIVER'      THEN 'HIPAA_TRAINING'
    WHEN 'CPR_FIRST_AID'              THEN 'CPR'
    WHEN 'DEFENSIVE_DRIVING'          THEN 'DEFENSIVE_DRIVING'
    WHEN 'FL_HOURS_OF_SERVICE'        THEN 'DUTY_STATUS_RECORD'
    WHEN 'FL_SSPP_DRIVER_RECORDS'     THEN 'SAFETY_TRAINING'
    ELSE NULL END
   SET c.credentialtypeid = t.recordid
 WHERE c.subject = 'driver';
