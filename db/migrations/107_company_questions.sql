-- ################################################################################################
-- # 107 - the questions a company answers, and the rules that hang off them.
-- #
-- # The matrix's conditional overlays could not be seeded in 106 because each needed a fact nobody
-- # had recorded. This adds the facts, and then the rules.
-- #
-- # THE QUESTIONS ARE DATA, not columns on `accounts`. A new question is a row, the same way a new
-- # rule is a row - otherwise every regulatory change is a schema migration and a backfill, which
-- # is the trap the old catalog was already in.
-- #
-- # SIX QUESTIONS, NOT EIGHT. The old catalog asked eight, and two of them were wrong:
-- #
-- #   Chapter 14-90 and the CTC programme were separate questions, but F.A.C. 41-2.006(2) pulls all
-- #   of chapter 14-90 onto a TD-funded operator, so they were never independent. One question now.
-- #
-- #   Wheelchair service was asked. It should not be: the fleet already records which vehicles have
-- #   a lift, so `fleet.wheelchair` is derived. Asking somebody to re-state a fact the system holds
-- #   is how the two answers drift apart.
-- #
-- # The old CHAPTER_14_90 question also asked whether the company "operates under Florida Chapter
-- # 14-90 bus transit rules" - which is the conclusion, not the question. 14-90.002(2) turns on CTC
-- # status, a continuous transit contract, or FDOT funding, so that is what is asked.
-- ################################################################################################

-- What a company can be asked. `factname` is how a rule refers to the answer.
CREATE TABLE IF NOT EXISTS companyquestions (
    code      VARCHAR(32)  NOT NULL,
    factname  VARCHAR(48)  NOT NULL,      -- the name rules use: company.medicaid, company.hipaa...
    question  VARCHAR(200) NOT NULL,
    help      VARCHAR(500) NULL,
    sortorder INT          NOT NULL DEFAULT 0,
    active    TINYINT(1)   NOT NULL DEFAULT 1,
    PRIMARY KEY (code),
    UNIQUE KEY ux_companyquestions_fact (factname)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- What one company has said. NULL answer = asked and not yet answered, which is not "no".
CREATE TABLE IF NOT EXISTS companyanswers (
    accountid VARCHAR(36) NOT NULL,
    code      VARCHAR(32) NOT NULL,
    answer    TINYINT(1)  NULL,
    updated   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedby VARCHAR(36) NULL,
    PRIMARY KEY (accountid, code),
    CONSTRAINT fk_companyanswers_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO companyquestions (code, factname, question, help, sortorder) VALUES
  ('MEDICAID_TRIPS', 'company.medicaid',
   'Do you carry Medicaid funded trips?',
   'Turns on the federal Medicaid driver requirements - exclusion screening against the OIG list every month, and Florida Level 1 background screening. 42 U.S.C. 1396a(a)(87).', 10),

  ('TRANSIT_CONTRACT', 'company.transit',
   'Do you work under a Community Transportation Coordinator, a continuous transit contract, or FDOT funding?',
   'This is what decides whether Florida Chapter 14-90 reaches you - not the size of your vehicles. A sedan under a CTC contract is covered; a full-size bus on private-pay work is not. F.A.C. 14-90.002(2). It also turns on the Transportation Disadvantaged testing records, because F.A.C. 41-2.006(2) pulls 14-90 onto a TD-funded operator.', 20),

  ('HIPAA_COVERED', 'company.hipaa',
   'Are you a HIPAA covered entity or a business associate?',
   'Decided by your agreements with plans, providers or brokers, and by how you handle protected health information. Turns on driver HIPAA training and the PHI acknowledgment.', 30),

  ('CRA_REPORTS', 'company.cra',
   'Do you obtain background reports from a consumer reporting agency?',
   'A third party running the checks, rather than you looking at public records yourself. Turns on the FCRA disclosure and authorisation, which must be signed BEFORE the report is pulled. 15 U.S.C. 1681b(b).', 40),

  ('EXPOSURE_DUTIES', 'company.exposure',
   'Do driver duties make contact with blood or other infectious material foreseeable?',
   'OSHA reaches an employee with occupational exposure. Carrying a passenger to an appointment does not by itself; particular assistance duties can. Turns on bloodborne pathogens training. 29 CFR 1910.1030.', 50),

  ('LEVEL2_REQUIRED', 'company.level2',
   'Does a broker, CTC or contract require Level 2 screening of your drivers?',
   'Florida law does NOT require this of NEMT drivers - F.S. 409.907(8)(a)4. expressly exempts them and requires Level 1 instead. Level 2 applies to you and your principals. Answer yes only if a contract demands it of drivers, in which case it is recorded as contractual rather than required.', 60);


-- Level 1 is name-based and is a different thing from the Level 2 fingerprint check, which the
-- catalog already had as FBI_FINGERPRINT. Keeping them apart matters: they do not substitute.
INSERT INTO credentialtypes (recordid, code, name, subject, category, description, active)
SELECT UUID(), 'FL_LEVEL1', 'Florida Level 1 background screening', 'driver', 'screening',
       'Name-based screening under s. 435.03 F.S. - employment history, statewide FDLE criminal check, and the Dru Sjodin national sex offender site.', 1
WHERE NOT EXISTS (SELECT 1 FROM credentialtypes WHERE code = 'FL_LEVEL1');


-- ------------------------------------------------------------------------------------------------
-- Corrections to the rules seeded in 106, now that the facts exist to condition them on.
-- ------------------------------------------------------------------------------------------------

-- These two are cited to the Medicaid statute, so they belong to companies carrying Medicaid trips.
UPDATE compliancerules SET applieswhen = '{"fact":"company.medicaid","is":true}'
 WHERE code IN ('MVR_FILE', 'DRIVER_LICENSE_COPY') AND effectiveto IS NULL;

-- Pointing at evidence that actually exists: the signed application is stored as 'APPLICATION',
-- and there is no report code for the annual Clearinghouse query - it is held as a credential.
UPDATE compliancerules SET evidencesource = 'signature:APPLICATION'
 WHERE code = 'EMPLOYMENT_APPLICATION' AND effectiveto IS NULL;
UPDATE compliancerules SET evidencesource = 'credential:CLEARINGHOUSE_QUERY'
 WHERE code = 'CLEARINGHOUSE' AND effectiveto IS NULL;


-- ------------------------------------------------------------------------------------------------
-- The conditional overlays. These come from the duty or the programme, not from the vehicle, so
-- they cut across all three tiers.
-- ------------------------------------------------------------------------------------------------
INSERT INTO compliancerules
  (recordid, code, name, subject, authoritytype, authority, jurisdiction, citation, applieswhen,
   evidencekind, evidencesource, reviewrequired, determination, blocking, duestage, recurrence,
   recurrencedays, sensitivity, retentionrule, effectivefrom, sortorder)
VALUES
  -- Medicaid. The monthly one is the only rule here where a stale answer is worse than none: an
  -- excluded driver makes every trip they carried an overpayment.
  (UUID(), 'EXCLUSION_CHECK_DRIVER', 'Exclusion screening - OIG LEIE and SAM.gov', 'driver',
   'statute', 'HHS OIG', 'US', '42 U.S.C. 1396a(a)(87)(A); 42 CFR 1001.1901',
   '{"fact":"company.medicaid","is":true}', 'query', 'credential:OIG_EXCLUSION', 0, 0, 1,
   'prehire', 'days', 31, 'normal', NULL, '2021-12-27', 400),

  (UUID(), 'FL_LEVEL1_DRIVER', 'Florida Level 1 background screening', 'driver', 'statute',
   'AHCA', 'FL', 'F.S. 409.907(8)(a)4.; F.S. 435.03',
   '{"fact":"company.medicaid","is":true}', 'query', 'credential:FL_LEVEL1', 0, 0, 1,
   'prehire', 'once', NULL, 'restricted', NULL, '2021-12-27', 410),

  -- Chapter 14-90 and the Transportation Disadvantaged programme, on one answer.
  (UUID(), 'FL_TRANSIT_MEDICAL', 'Bus transit medical examination (FDOT 725-030-11)', 'driver',
   'regulation', 'FDOT', 'FL', 'F.A.C. 14-90.0041',
   '{"fact":"company.transit","is":true}', 'document', 'credential:TRANSIT_MEDICAL', 0, 0, 1,
   'prehire', 'days', 730, 'restricted', 'Held 4 years - F.A.C. 14-90.0041', '2024-01-01', 500),

  (UUID(), 'FL_LICENSE_STATUS_NOTICE', 'Licence suspension reporting acknowledgement', 'driver',
   'regulation', 'FDOT', 'FL', 'F.A.C. 14-90.006(1)',
   '{"fact":"company.transit","is":true}', 'attestation', NULL, 0, 0, 0,
   'prehire', 'once', NULL, 'normal', NULL, '2024-01-01', 510),

  (UUID(), 'FL_SSPP_DRIVER_RECORDS', 'Driver selection and training records (SSPP)', 'driver',
   'regulation', 'FDOT', 'FL', 'F.A.C. 14-90.004(1)',
   '{"fact":"company.transit","is":true}', 'document', 'credential:SAFETY_TRAINING', 0, 0, 1,
   'ongoing', 'once', NULL, 'normal', 'Held 4 years - F.A.C. 14-90.004', '2024-01-01', 520),

  (UUID(), 'FL_HOURS_OF_SERVICE', 'Hours of service record (12 h driving, 16 h duty, 72 h/7 days)',
   'driver', 'regulation', 'FDOT', 'FL', 'F.A.C. 14-90.006(3), (5)',
   '{"fact":"company.transit","is":true}', 'document', 'credential:DUTY_STATUS_RECORD', 0, 0, 1,
   'ongoing', 'once', NULL, 'normal', 'Held 4 years - F.A.C. 14-90.006', '2024-01-01', 530),

  (UUID(), 'FL_TD_DRUG_TESTING', 'Drug and alcohol testing records (safety-sensitive)', 'driver',
   'regulation', 'CTD', 'FL', 'F.A.C. 41-2.006(4)(a)',
   '{"fact":"company.transit","is":true}', 'test', 'drugtest:preemployment', 0, 1, 1,
   'prehire', 'perhire', NULL, 'restricted', '5 years - 49 CFR 382.401(b)', '2024-01-01', 540),

  -- HIPAA.
  (UUID(), 'HIPAA_TRAINING_DRIVER', 'HIPAA training certificate', 'driver', 'regulation', 'HHS OCR',
   'US', '45 CFR 164.530(b)(1)', '{"fact":"company.hipaa","is":true}', 'document',
   'credential:HIPAA_TRAINING', 0, 0, 1, 'prehire', 'days', 365, 'normal', NULL, '2013-09-23', 600),

  (UUID(), 'PHI_CONFIDENTIALITY', 'PHI confidentiality acknowledgment', 'driver', 'policy',
   'Company policy', 'US', '45 CFR 164.530(b)', '{"fact":"company.hipaa","is":true}', 'document',
   'signature:PHI_ACK', 0, 0, 0, 'prehire', 'once', NULL, 'normal', NULL, '2013-09-23', 610),

  -- Wheelchair work. Derived from the fleet, not asked - the lift is already recorded per vehicle.
  (UUID(), 'PASS_TRAINING', 'Passenger assistance and equipment proficiency training', 'driver',
   'regulation', 'FTA', 'US', '49 CFR 37.173', '{"fact":"fleet.wheelchair","is":true}', 'document',
   'credential:PASSENGER_ASSIST', 0, 0, 1, 'prehire', 'once', NULL, 'normal', NULL, '1991-01-26', 700),

  (UUID(), 'SECUREMENT_TRAINING_CERT', 'Wheelchair securement training certificate', 'driver',
   'regulation', 'FTA', 'US', '49 CFR 37.173; F.A.C. 14-90.004(1)',
   '{"fact":"fleet.wheelchair","is":true}', 'document', 'credential:WHEELCHAIR_SECUREMENT', 0, 0, 1,
   'prehire', 'days', 730, 'normal', NULL, '1991-01-26', 710),

  -- OSHA.
  (UUID(), 'BBP_TRAINING', 'Bloodborne pathogens training', 'driver', 'regulation', 'OSHA', 'US',
   '29 CFR 1910.1030', '{"fact":"company.exposure","is":true}', 'document',
   'credential:BLOODBORNE_PATHOGENS', 0, 0, 1, 'prehire', 'days', 365, 'normal',
   'Held 3 years - 29 CFR 1910.1030(h)(2)(ii)', '1992-03-06', 800),

  -- FCRA. The consent has to be dated before the report was pulled, which is a sequence the
  -- evaluator cannot yet check - it only knows the consent exists.
  (UUID(), 'FCRA_FORMS', 'FCRA disclosure and authorisation', 'driver', 'statute', 'CFPB', 'US',
   '15 U.S.C. 1681b(b)', '{"fact":"company.cra","is":true}', 'document', 'signature:FCRA_AUTH',
   0, 0, 1, 'prehire', 'perhire', NULL, 'normal', NULL, '1997-09-30', 900),

  -- Level 2, which Florida does not ask of NEMT drivers. Contractual, and not blocking.
  (UUID(), 'FL_LEVEL2_DRIVER', 'Level 2 fingerprint screening (by contract)', 'driver', 'contract',
   'Broker or CTC', 'FL', 'F.S. 435.04 - not required of NEMT drivers by F.S. 409.907(8)(a)4.',
   '{"fact":"company.level2","is":true}', 'query', 'credential:FBI_FINGERPRINT', 0, 0, 0,
   'prehire', 'days', 1825, 'restricted', NULL, '2024-01-01', 910);
