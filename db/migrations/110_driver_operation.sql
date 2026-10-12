-- ################################################################################################
-- # 110 - what the DRIVER will operate, not what the yard currently holds.
-- #
-- # 106 keyed Part 391 and Part 382 off the fleet: if any vehicle on the account was a commercial
-- # motor vehicle, every driver owed what that vehicle brought with it. The reasoning was that
-- # before hire there is no trip and no assignment, so the fleet is the only thing to judge against.
-- #
-- # That is wrong, and wrong in a way that would have hurt. Buying a bus would have silently
-- # disqualified every driver on the roster overnight, and selling it would have silently
-- # re-qualified them. Qualification is not supposed to move because of a purchase order. A company
-- # that intends to buy a sixteen-seat bus next quarter needs to qualify its drivers for it now -
-- # the whole point of a qualification file is that it is ready before the driver is needed.
-- #
-- # The regulations key off what the driver operates, so that is what is asked. Three independent
-- # facts, because three independent thresholds decide different things:
-- #
-- #   operatescmv    a commercial motor vehicle under 49 CFR 390.5 -> Part 391 reaches them
-- #   operatescdl    a vehicle requiring a CDL under 49 CFR 383.91 -> Part 382 reaches them
-- #   operatesheavy  26,001 lb or more -> decides which side of F.S. 316.302(2)(f) they fall
-- #
-- # They are independent on purpose. A sixteen-seat bus at 14,500 lb needs a CDL and is not heavy;
-- # a 30,000 lb straight truck is heavy and carries five people. Collapsing them into one "level"
-- # would lose exactly the cases this application exists to get right.
-- #
-- # The fleet facts stay, and stay useful - they are what the vehicle screen reports, and they are
-- # how the driver page can say "you run something this driver is not qualified for". They just do
-- # not decide anybody's qualification any more.
-- ################################################################################################

ALTER TABLE drivers
    ADD COLUMN IF NOT EXISTS operatescdl   TINYINT(1) NULL AFTER operatescmv,
    ADD COLUMN IF NOT EXISTS operatesheavy TINYINT(1) NULL AFTER operatescdl;

-- Part 391 follows the vehicle being a commercial motor vehicle, whoever is driving it.
UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"operation.interstate","is":true},{"fact":"driver.cmv","is":true}]}'
 WHERE effectiveto IS NULL AND code IN
   ('DQ_FILE', 'EMPLOYMENT_APPLICATION', 'MVR_PREEMPLOYMENT', 'SAFETY_PERFORMANCE_CONSENT',
    'SAFETY_PERFORMANCE_HISTORY', 'ROAD_TEST', 'MEDICAL_CERT', 'MVR_ANNUAL');

-- Part 382 follows the CDL - 49 CFR 382.103(a)(1) - and nothing else.
UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"operation.interstate","is":true},{"fact":"driver.cdl","is":true}]}'
 WHERE effectiveto IS NULL AND code IN
   ('PREEMPLOYMENT_DRUG_TEST', 'CLEARINGHOUSE_PREEMP', 'CLEARINGHOUSE', 'CLEARINGHOUSE_CONSENT',
    'DA_POLICY_RECEIPT', 'RANDOM_TESTING_RECORDS');

-- Florida intrastate, under 26,001 lb: F.S. 316.302(2)(f) drops Part 391 and keeps Part 382.
UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"operation.interstate","is":false},{"fact":"driver.cmv","is":true},{"fact":"driver.heavy","is":false}]}'
 WHERE effectiveto IS NULL AND code = 'FL_INTRASTATE_382';

-- Florida intrastate, 26,001 lb and over: F.S. 316.302(1)(b) applies the lot, frozen at 31 Dec 2023.
UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"operation.interstate","is":false},{"fact":"driver.cmv","is":true},{"fact":"driver.heavy","is":true}]}'
 WHERE effectiveto IS NULL AND code = 'FL_INTRASTATE_FULL';
