-- ################################################################################################
-- # 345 - from the third review (2026-10-22).
-- ################################################################################################

-- A state's Medicaid NEMT rules reach a company because it carries for THAT state's program - it
-- has a Medicaid payer line there - not because the state is somewhere it drives. A Florida
-- Medicaid provider whose vans cross into Georgia, with no Georgia Medicaid line, was being held
-- to every Georgia NEMT rule. On a trip, the trip's own payer line names the state (app/tripcheck.py).
UPDATE compliancerules SET applieswhen = '{"fact":"company.medicaidstates","has":"GA"}'
 WHERE accountid IS NULL AND effectiveto IS NULL AND code LIKE 'GA\_NET\_%'
   AND applieswhen LIKE '%company.medicaid"%';

UPDATE compliancerules SET applieswhen = '{"fact":"company.medicaidstates","has":"FL"}'
 WHERE code = 'FL_LEVEL1_DRIVER' AND accountid IS NULL AND effectiveto IS NULL;

-- 49 CFR 396.11(a)(1): a motor carrier operating only one commercial motor vehicle does not
-- prepare driver vehicle inspection reports.
UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"vehicle.cmv_federal","is":true},{"fact":"fleet.multiplecmv","is":true}]}'
 WHERE code = 'DVIR' AND accountid IS NULL AND effectiveto IS NULL;

-- 49 CFR 37.163 is lift maintenance by public entities; nothing found requires a periodic load test
-- certificate. Kept for the company whose contract, insurer or manufacturer asks for one, and
-- reaches nobody until the company adopts it.
UPDATE compliancerules SET offered = 1,
       note = 'Offered 2026-10-22: no regulation found requiring a periodic lift load test; adopt it where a contract, insurer or manufacturer does.'
 WHERE code = 'LIFT_LOAD_TEST' AND accountid IS NULL AND effectiveto IS NULL;
