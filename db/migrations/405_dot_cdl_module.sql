-- ################################################################################################
-- # 405 - DOT & CDL Compliance becomes a paid add-on, and every rule says which of five
-- # categories it belongs to.
-- #
-- #   FEDERAL_NEMT   Federal NEMT regulations: Medicaid safeguards, ADA, HIPAA, OSHA, FCRA, I-9/W-4
-- #   STATE_NEMT     State NEMT regulations: state Medicaid, state transit, state licensing and law
-- #   COMPANY        The company's own requirements
-- #   BROKER_PAYER   Broker and payer contracts
-- #   FMCSA_DOT      FMCSA / DOT and CDL: Parts 382, 383, 390, 391, 395, 396 and Florida's adoption
-- #                  of them. Evaluated only for an account with the module switched on.
-- #
-- # Whether a DOT rule reaches a vehicle is still decided by the vehicle and the operation. The
-- # module decides only whether TripProof manages it; without it, a vehicle DOT rules reach is
-- # refused for dispatch (rules.py) rather than treated as if nothing were owed.
-- ################################################################################################

ALTER TABLE accounts
  ADD COLUMN IF NOT EXISTS dotmodule      TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS dotmodulesince DATETIME   NULL;

-- Accounts already on file keep what they have been tracking. New accounts start without it.
UPDATE accounts SET dotmodule = 1, dotmodulesince = UTC_TIMESTAMP()
 WHERE dotmodulesince IS NULL AND platform = 0;

-- The old five categories, carried across.
UPDATE compliancerules SET authoritycategory = CASE authoritycategory
    WHEN 'FEDERAL_GENERAL'  THEN 'FEDERAL_NEMT'
    WHEN 'FEDERAL_MEDICAID' THEN 'FEDERAL_NEMT'
    WHEN 'STATE_GENERAL'    THEN 'STATE_NEMT'
    WHEN 'STATE_MEDICAID'   THEN 'STATE_NEMT'
    WHEN 'CONTRACT_COMPANY' THEN 'BROKER_PAYER'
    ELSE authoritycategory END
 WHERE authoritycategory IN ('FEDERAL_GENERAL', 'FEDERAL_MEDICAID', 'STATE_GENERAL',
                             'STATE_MEDICAID', 'CONTRACT_COMPANY');

-- Rules that never had one: by who demands them.
UPDATE compliancerules SET authoritycategory = CASE
    WHEN authoritytype = 'contract' THEN 'BROKER_PAYER'
    WHEN authoritytype = 'policy'   THEN 'COMPANY'
    WHEN jurisdiction <> 'US'       THEN 'STATE_NEMT'
    ELSE 'FEDERAL_NEMT' END
 WHERE authoritycategory IS NULL;

-- A company's own rules are the company's.
UPDATE compliancerules SET authoritycategory = 'COMPANY'
 WHERE accountid IS NOT NULL AND authoritytype <> 'contract';

-- FMCSA / DOT and CDL.
UPDATE compliancerules SET authoritycategory = 'FMCSA_DOT'
 WHERE code IN (
   -- company
   'USDOT_AUTHORITY', 'MCS90B', 'MCS150', 'UCR', 'DER_DESIGNATION', 'RANDOM_TESTING_PROGRAM',
   'SUPERVISOR_TRAINING', 'DA_MIS_REPORT', 'TPA_AGREEMENT', 'CLEARINGHOUSE_REGISTRATION',
   'DRUG_ALCOHOL_POLICY',
   -- driver
   'DA_PROHIBITION', 'DRIVER_AGE', 'EMPLOYMENT_APPLICATION', 'ENGLISH_PROFICIENCY',
   'LICENSE_ENDORSEMENTS', 'MEDICAL_CERT', 'CDL_MEDICAL_STATUS', 'SPE_CERTIFICATE', 'ELDT',
   'MVR_PREEMPLOYMENT', 'SAFETY_PERFORMANCE_CONSENT', 'SAFETY_PERFORMANCE_HISTORY', 'ROAD_TEST',
   'MVR_ANNUAL', 'PREEMPLOYMENT_DRUG_TEST', 'CLEARINGHOUSE_CONSENT', 'PREEMP_DA_QUESTIONNAIRE',
   'PRIOR_VIOLATION_RTD', 'POSTACCIDENT_TEST', 'CLEARINGHOUSE_PREEMP', 'RANDOM_TEST_OWED',
   'FOLLOWUP_TESTING', 'CLEARINGHOUSE', 'DA_POLICY_RECEIPT', 'PREV7_ONDUTY',
   'RANDOM_TESTING_RECORDS', 'FL_INTRASTATE_AGE18', 'FL_INTRASTATE_382', 'FL_INTRASTATE_FULL',
   -- vehicle
   'DOT_ANNUAL_INSPECTION', 'DVIR', 'MAINTENANCE_RECORDS')
   AND accountid IS NULL;

-- The company's own policies.
UPDATE compliancerules SET authoritycategory = 'COMPANY'
 WHERE code IN ('WORKPLACE_POLICY', 'PHI_CONFIDENTIALITY') AND accountid IS NULL;

-- Georgia's Death Master File check is the Georgia DCH NEMT manual (608.7), not a contract.
UPDATE compliancerules SET authoritycategory = 'STATE_NEMT'
 WHERE code = 'GA_NET_DMF' AND accountid IS NULL;

-- Every driver needs a license and every company needs auto liability cover, DOT-regulated or not.
-- They were cited to FMCSA; the duty every NEMT company has is State law.
UPDATE compliancerules
   SET authoritycategory = 'STATE_NEMT', authoritytype = 'statute', authority = 'State law',
       citation = 'State driver licensing law', sourceurl = NULL
 WHERE code = 'DRIVER_LICENSE' AND accountid IS NULL AND effectiveto IS NULL;
UPDATE compliancerules
   SET authoritycategory = 'STATE_NEMT', authoritytype = 'statute', authority = 'State law',
       citation = 'State financial responsibility law', sourceurl = NULL
 WHERE code = 'AUTO_LIABILITY' AND accountid IS NULL AND effectiveto IS NULL;

-- Enforcement is no longer a setting: every applicable approved requirement refuses the trip.
UPDATE companyprofiles SET enforcetripcheck = 1;
ALTER TABLE companyprofiles ALTER COLUMN enforcetripcheck SET DEFAULT 1;
