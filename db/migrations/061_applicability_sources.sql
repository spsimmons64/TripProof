-- ################################################################################################
-- # 061 - where a requirement comes from, as a field rather than as a guess.
-- #
-- # The catalog had one flat list, so a rule that reaches one kind of operation read as a rule for
-- # every driver: Part 391 sat beside Medicaid's minimum driver framework, and Chapter 14-90 beside
-- # both. Every requirement now names the body of law it comes from, and requirements are read in
-- # that order - federal, then Florida, then Medicaid/AHCA, then the CTC, then the payer's contract,
-- # then the employer's own policy.
-- #
-- # `classification` is what the source makes of it, kept apart from what a company then decides:
-- #   required      the source makes it apply to this driver
-- #   conditional   it applies only when the condition in `appliesif` holds
-- #   contractual   no law imposes it; a broker, payer or contract may
-- #   notrequired   no applicable requirement, kept so the answer is on the record
-- ################################################################################################
CREATE TABLE IF NOT EXISTS compliancesources (
    code        VARCHAR(24)  NOT NULL,
    name        VARCHAR(96)  NOT NULL,
    authority   VARCHAR(160) NOT NULL,
    reach       VARCHAR(255) NOT NULL,        -- who this body of law actually reaches
    sortorder   INT          NOT NULL DEFAULT 0,
    PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO compliancesources (code, name, authority, reach, sortorder) VALUES
 ('FED_MEDICAID',   'Federal - Medicaid NEMT', 'Social Security Act 1902(a)(87); 42 CFR 440.170',
  'Every driver carrying Medicaid non-emergency transportation', 10),
 ('FED_EMPLOYMENT', 'Federal - employment', '8 CFR 274a.2; 26 CFR 31.3402(f)(2)-1',
  'Every employee of a United States employer', 20),
 ('FED_FCRA',       'Federal - FCRA', '15 U.S.C. 1681b(b)',
  'An employer that obtains a background report from a consumer reporting agency', 30),
 ('FED_OSHA',       'Federal - OSHA', '29 CFR 1910.1030',
  'An employee whose duties make contact with blood or other infectious materials foreseeable', 40),
 ('FED_HIPAA',      'Federal - HIPAA', '45 CFR 164',
  'A covered entity or a business associate handling protected health information', 50),
 ('FED_ADA',        'Federal - ADA / FTA', '49 CFR 37.173',
  'Personnel of a covered transportation entity who operate equipment or assist passengers with disabilities', 60),
 ('FED_FMCSA',      'Federal - FMCSA', '49 CFR parts 382 and 391',
  'A driver of a commercial motor vehicle as those parts define it', 70),
 ('FL_AHCA',        'Florida - Medicaid / AHCA', 'F.A.C. 59G-4.330; F.S. 408.809; F.S. 435.04',
  'A Florida Medicaid transportation provider, and screening the statutes reach', 80),
 ('FL_CTC',         'Florida - Transportation Disadvantaged', 'F.S. chapter 427; F.A.C. 41-2',
  'An operator under a Community Transportation Coordinator', 90),
 ('FL_14_90',       'Florida - bus transit safety', 'F.A.C. chapter 14-90',
  'A covered bus transit system, and the drivers and vehicles in it', 100),
 ('CONTRACT',       'Broker, payer or contract', 'The agreement itself',
  'Whatever a broker, managed care plan, facility or payer writes into its contract', 110),
 ('EMPLOYER',       'The company itself', 'Company policy',
  'Nothing imposes it; a company keeps it because it wants to', 120);

ALTER TABLE compliancedocs
    ADD COLUMN sourcecode     VARCHAR(24)  NULL AFTER jurisdiction,
    ADD COLUMN classification VARCHAR(12)  NULL AFTER obligation,
    ADD COLUMN whendue        VARCHAR(120) NULL AFTER renewal,
    ADD COLUMN retention      VARCHAR(80)  NULL AFTER whendue;

-- Where each of today's driver requirements actually comes from.
UPDATE compliancedocs SET sourcecode = CASE code
    WHEN 'I9'                         THEN 'FED_EMPLOYMENT'
    WHEN 'W4'                         THEN 'FED_EMPLOYMENT'
    WHEN 'DRIVER_LICENSE_COPY'        THEN 'FED_MEDICAID'
    WHEN 'MVR_FILE'                   THEN 'FED_MEDICAID'
    WHEN 'EXCLUSION_CHECK_DRIVER'     THEN 'FED_MEDICAID'
    WHEN 'DRUG_LAW_PROCESS'           THEN 'FED_MEDICAID'
    WHEN 'DRIVING_HISTORY_PROCESS'    THEN 'FED_MEDICAID'
    WHEN 'FCRA_FORMS'                 THEN 'FED_FCRA'
    WHEN 'BBP_TRAINING'               THEN 'FED_OSHA'
    WHEN 'HIPAA_TRAINING_DRIVER'      THEN 'FED_HIPAA'
    WHEN 'PHI_CONFIDENTIALITY'        THEN 'FED_HIPAA'
    WHEN 'PASS_TRAINING'              THEN 'FED_ADA'
    WHEN 'SECUREMENT_TRAINING_CERT'   THEN 'FED_ADA'
    WHEN 'PASSENGER_SERVICE_ACK'      THEN 'FED_ADA'
    WHEN 'EMPLOYMENT_APPLICATION'     THEN 'FED_FMCSA'
    WHEN 'MVR_PREEMPLOYMENT'          THEN 'FED_FMCSA'
    WHEN 'MVR_ANNUAL'                 THEN 'FED_FMCSA'
    WHEN 'SAFETY_PERFORMANCE_HISTORY' THEN 'FED_FMCSA'
    WHEN 'MEDICAL_CERT'               THEN 'FED_FMCSA'
    WHEN 'ROAD_TEST'                  THEN 'FED_FMCSA'
    WHEN 'DQ_FILE'                    THEN 'FED_FMCSA'
    WHEN 'FL_INTRASTATE_DQ'           THEN 'FED_FMCSA'
    WHEN 'CLEARINGHOUSE'              THEN 'FED_FMCSA'
    WHEN 'CLEARINGHOUSE_PREEMP'       THEN 'FED_FMCSA'
    WHEN 'CLEARINGHOUSE_CONSENT'      THEN 'FED_FMCSA'
    WHEN 'DA_POLICY_RECEIPT'          THEN 'FED_FMCSA'
    WHEN 'PREEMPLOYMENT_DRUG_TEST'    THEN 'FED_FMCSA'
    WHEN 'RANDOM_TESTING_RECORDS'     THEN 'FED_FMCSA'
    WHEN 'DA_TESTING_PROGRAM'         THEN 'FED_FMCSA'
    WHEN 'PSP_REPORT'                 THEN 'FED_FMCSA'
    WHEN 'CDLIS_CHECK'                THEN 'FED_FMCSA'
    WHEN 'FL_LEVEL2_DRIVER'           THEN 'FL_AHCA'
    WHEN 'FL_TRANSIT_MEDICAL'         THEN 'FL_14_90'
    WHEN 'FL_SSPP_DRIVER_RECORDS'     THEN 'FL_14_90'
    WHEN 'FL_HOURS_OF_SERVICE'        THEN 'FL_14_90'
    WHEN 'FL_LICENSE_STATUS_NOTICE'   THEN 'FL_14_90'
    WHEN 'FL_TD_DRUG_TESTING'         THEN 'FL_CTC'
    WHEN 'CRIMINAL_BACKGROUND'        THEN 'CONTRACT'
    WHEN 'SEX_OFFENDER_CHECK'         THEN 'CONTRACT'
    WHEN 'ABUSE_REGISTRY_CHECK'       THEN 'CONTRACT'
    WHEN 'DRUG_SCREEN_NONCDL'         THEN 'CONTRACT'
    ELSE 'EMPLOYER' END
WHERE subject = 'driver';

-- What the source makes of it today; the corrections that follow restate several of these.
UPDATE compliancedocs
   SET classification = CASE obligation
        WHEN 'required'    THEN 'required'
        WHEN 'conditional' THEN 'conditional'
        ELSE 'contractual' END
 WHERE subject = 'driver';
