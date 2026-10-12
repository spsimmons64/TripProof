-- ################################################################################################
-- # 136 - a Florida rule needs Florida in it.
-- #
-- # Every one of these is Florida law - F.S. 435.03, F.S. 316.302, F.A.C. Chapter 14-90, F.A.C.
-- # 41-2.006, FDOT 725-030-11 - and not one of them asked where the company is. They keyed off what
-- # the company DOES (Medicaid trips, a CTC contract, covered buses), which is the right second
-- # question and cannot be the first: a Kansas operator carrying Medicaid trips was being asked for
-- # a Florida Level 1 screening under a Florida statute that does not reach them.
-- #
-- # `company.state` is added as the first test in each. Where the state is not recorded the fact is
-- # unknown, so the rule reads as undecided rather than silently reaching everybody - which is the
-- # whole point of the facts being three-valued.
-- #
-- # SECUREMENT_TRAINING_CERT is deliberately NOT in this list. It is cited to 49 CFR 37.173 first
-- # and F.A.C. 14-90.004(1) second: the federal requirement reaches a wheelchair-carrying operator
-- # in any state, and the Florida citation is an additional authority, not the only one.
-- ################################################################################################

UPDATE compliancerules SET applieswhen =
  '{"all":[{"fact":"company.state","eq":"FL"},{"fact":"driver.chapter1490","is":true}]}'
 WHERE code IN ('FL_HOURS_OF_SERVICE', 'FL_SSPP_DRIVER_RECORDS', 'FL_TRANSIT_MEDICAL');

UPDATE compliancerules SET applieswhen =
  '{"all":[{"fact":"company.state","eq":"FL"},{"fact":"operation.interstate","is":false},
           {"fact":"driver.cmv","is":true},{"fact":"driver.heavy","is":false}]}'
 WHERE code = 'FL_INTRASTATE_382';

UPDATE compliancerules SET applieswhen =
  '{"all":[{"fact":"company.state","eq":"FL"},{"fact":"operation.interstate","is":false},
           {"fact":"driver.cmv","is":true},{"fact":"driver.heavy","is":true}]}'
 WHERE code = 'FL_INTRASTATE_FULL';

UPDATE compliancerules SET applieswhen =
  '{"all":[{"fact":"company.state","eq":"FL"},{"fact":"company.medicaid","is":true}]}'
 WHERE code = 'FL_LEVEL1_DRIVER';

UPDATE compliancerules SET applieswhen =
  '{"all":[{"fact":"company.state","eq":"FL"},{"fact":"company.level2","is":true}]}'
 WHERE code = 'FL_LEVEL2_DRIVER';

UPDATE compliancerules SET applieswhen =
  '{"all":[{"fact":"company.state","eq":"FL"},{"fact":"company.transit","is":true}]}'
 WHERE code = 'FL_TD_DRUG_TESTING';

UPDATE compliancerules SET applieswhen =
  '{"all":[{"fact":"company.state","eq":"FL"},{"fact":"driver.chapter1490","is":true},
           {"fact":"driver.licenceaction","is":true}]}'
 WHERE code = 'FL_LICENSE_STATUS_NOTICE';
