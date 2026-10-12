-- Who a regulation reaches is one question. It is now asked in one place.
--
-- Thirty-one rules each carried their own hand-written answer to "do the federal motor carrier
-- safety regulations reach this operation?", and twelve of them answered it with
-- `operation.interstate` - do you ever drive across a state line. That is not what decides it.
--
-- The catalog therefore held both of these about the same carrier on the same day:
--
--   * Tim Horton, prohibited from safety-sensitive work under 49 CFR Part 382, program `dot`,
--     a hard stop on the dashboard.
--   * The company told that the drug and alcohol policy, the DER designation, the random
--     selections, the supervisor training and the Clearinghouse registration - the Part 382
--     programme itself - did not reach it.
--
-- A carrier cannot owe a Part 382 prohibition on its driver and owe no Part 382 programme. Each
-- of those rules was defensible read on its own; they were wrong against each other, which is
-- the one thing reading them one at a time can never show.
--
-- WHAT ACTUALLY DECIDES IT
--
-- 49 CFR 390.3(a) for interstate, and then the State. Florida adopts the federal motor carrier
-- safety regulations for intrastate operation of vehicles rated 26,001 lb or more -
-- F.S. 316.302(1)(b) - which is the same statute FL_INTRASTATE_FULL has always cited AT THE
-- DRIVER. It was applied there and nowhere else, so the carrier running those very drivers was
-- told the federal rules missed it.
--
-- app/facts.py now computes that once, per subject, three-valued:
--
--   reach.fmcsr      subject to the FMCSRs - interstate, or by State adoption
--   reach.part382    the drug and alcohol programme: reach.fmcsr and CDL-required operation
--   reach.part390    accident register and the rest of Part 390
--   reach.part391    driver qualification
--   reach.authority  operating authority and registration, which ARE about interstate carriage
--                    itself rather than about which safety rules a State has adopted, and so
--                    stay on the state line
--
-- Per subject matters: a carrier with one 26,001 lb unit is reached, while the driver who only
-- takes out a 12,000 lb van is not reached by F.S. 316.302(1)(b) at all. Answering the driver
-- from the company's reach would pull the whole of Part 391 onto a van driver - the mirror image
-- of this bug, and just as wrong.
--
-- A rule may still add its OWN trigger on top: a prohibition fires on driver.prohibited, a
-- post-accident test on driver.postaccidentowed. What it may no longer do is re-decide who the
-- regulation reaches. api/tests/test_catalog.py fails the build when one tries.
--
-- NOT CHANGED: FL_INTRASTATE_382 and FL_INTRASTATE_FULL. Those are about the State adoption
-- itself, so being written in terms of operation.interstate is what they are for.

-- ------------------------------------------------------------------------------------------
-- The company: the Part 382 programme
-- ------------------------------------------------------------------------------------------
UPDATE compliancerules
   SET applieswhen = '{"fact":"reach.part382","is":true}'
 WHERE code IN ('CLEARINGHOUSE_REGISTRATION', 'DER_DESIGNATION', 'DRUG_ALCOHOL_POLICY',
                'RANDOM_SELECTIONS', 'RANDOM_TESTING_PROGRAM', 'SUPERVISOR_TRAINING',
                -- 49 CFR 40 service agent. There is no third-party administrator to appoint
                -- where there is no programme to administer.
                'TPA_AGREEMENT')
   AND subject = 'company';

-- ------------------------------------------------------------------------------------------
-- The company: Part 390
-- ------------------------------------------------------------------------------------------
UPDATE compliancerules
   SET applieswhen = '{"fact":"reach.part390","is":true}'
 WHERE code = 'ACCIDENT_REGISTER' AND subject = 'company';

-- ------------------------------------------------------------------------------------------
-- The company: operating authority. Same answer as before - these really are about crossing a
-- state line - but said by name, so the next reader can tell a deliberate interstate test from
-- one that was reached for because it was the nearest fact to hand.
-- ------------------------------------------------------------------------------------------
UPDATE compliancerules
   SET applieswhen = '{"fact":"reach.authority","is":true}'
 WHERE code IN ('MCS150', 'USDOT_AUTHORITY', 'UCR', 'MCS90B') AND subject = 'company';

-- ------------------------------------------------------------------------------------------
-- The driver: Part 382 and the Part 40 procedures that run with it. reach.part382 already
-- carries the CDL test at driver level, so the rules no longer repeat it.
-- ------------------------------------------------------------------------------------------
UPDATE compliancerules
   SET applieswhen = '{"fact":"reach.part382","is":true}'
 WHERE code IN ('CLEARINGHOUSE', 'CLEARINGHOUSE_CONSENT', 'CLEARINGHOUSE_PREEMP',
                'DA_POLICY_RECEIPT', 'PREEMPLOYMENT_DRUG_TEST', 'RANDOM_TESTING_RECORDS',
                'PREEMP_DA_QUESTIONNAIRE')
   AND subject = 'driver';

-- 49 CFR 40.25(j) - reach, plus this rule's own trigger.
UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"reach.part382","is":true},'
                     '{"fact":"driver.priorviolation","is":true}]}'
 WHERE code = 'PRIOR_VIOLATION_RTD' AND subject = 'driver';

-- ------------------------------------------------------------------------------------------
-- The driver: Part 391 qualification. reach.part391 carries the CMV test.
-- ------------------------------------------------------------------------------------------
UPDATE compliancerules
   SET applieswhen = '{"fact":"reach.part391","is":true}'
 WHERE code IN ('DRIVER_AGE', 'EMPLOYMENT_APPLICATION', 'ENGLISH_PROFICIENCY', 'MEDICAL_CERT',
                'MVR_ANNUAL', 'MVR_PREEMPLOYMENT', 'ROAD_TEST', 'SAFETY_PERFORMANCE_CONSENT',
                'SAFETY_PERFORMANCE_HISTORY')
   AND subject = 'driver';

-- What the licensing State holds on a CDL driver, so the CDL test is this rule's own and is
-- kept alongside the reach test rather than folded into it.
UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"reach.part391","is":true},'
                     '{"fact":"driver.cdl","is":true}]}'
 WHERE code = 'CDL_MEDICAL_STATUS' AND subject = 'driver';

-- ------------------------------------------------------------------------------------------
-- The driver: Part 395 hours of service, which Florida adopts on the same hook as Part 391.
-- ------------------------------------------------------------------------------------------
UPDATE compliancerules
   SET applieswhen = '{"fact":"reach.fmcsr","is":true}'
 WHERE code = 'PREV7_ONDUTY' AND subject = 'driver';
