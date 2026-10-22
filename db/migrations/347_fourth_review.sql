-- ################################################################################################
-- # 347 - from the fourth review (2026-10-22).
-- ################################################################################################

-- 49 CFR 382.303 says when a post-accident test is owed and how fast; it does not remove the driver
-- from duty while the result is awaited. A refusal or a positive result is a violation and is a
-- prohibition (driver.prohibited), which does stop the driver. The owed test is a task with a
-- deadline, not a bar.
UPDATE compliancerules SET blocking = 0
 WHERE code = 'POSTACCIDENT_TEST' AND accountid IS NULL AND effectiveto IS NULL;

-- F.S. 409.907(8)(a)4 asks for a Level 1 screening of each NEMT driver (or, for a transportation
-- network company's drivers, procedures AHCA finds equivalent - F.S. 316.87(2)). A screening on file
-- answers it only once somebody has read the result.
UPDATE compliancerules SET reviewrequired = 1,
       description = 'Florida Medicaid NEMT drivers are not subject to Level 2 screening but must complete a Level 1 background screening under chapter 435 (F.S. 409.907(8)(a)4; F.S. 435.03). A transportation network company''s drivers may instead be screened by procedures AHCA determines to be functionally equivalent (F.S. 316.87(2)). The screening on file counts once somebody has read that the result is eligible.'
 WHERE code = 'FL_LEVEL1_DRIVER' AND accountid IS NULL AND effectiveto IS NULL;

-- Not a regulation: 49 CFR 37.163 is keeping lifts in working order, and sets no load test. Offered
-- (346) for the company whose contract, insurer or lift manufacturer asks for one.
UPDATE compliancerules SET authoritytype = 'contract', authority = 'Contract, insurer or manufacturer',
       authoritycategory = 'CONTRACT_COMPANY', citation = NULL,
       description = 'A periodic load test of the lift fitted to this vehicle, where a contract, an insurer or the lift''s manufacturer asks for one. No regulation sets one: 49 CFR 37.163 requires lifts to be kept in operative condition and repaired promptly, which is the vehicle''s own maintenance record.'
 WHERE code = 'LIFT_LOAD_TEST' AND accountid IS NULL AND effectiveto IS NULL;

-- The due text was copied from the bloodborne pathogens plan. DCH 701.1.4: registered or licensed
-- where required, for the term of the service agreement.
UPDATE compliancerules SET duetext = 'Kept current for the term of the service agreement, where registration is required'
 WHERE code = 'GA_NET_PROVIDER_REGISTRATION' AND accountid IS NULL AND effectiveto IS NULL;
