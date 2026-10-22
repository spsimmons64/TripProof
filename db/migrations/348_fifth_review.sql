-- ################################################################################################
-- # 348 - from the fifth review (2026-10-22). Read against 49 CFR 396.11 (law.cornell.edu).
-- ################################################################################################

-- 396.11(a)(2)(i): no report is required where no defect or deficiency is discovered or reported.
-- 396.11(a)(3): a defect likely to affect safe operation is repaired, and the repair certified,
-- before the vehicle is operated again. 396.11(a)(5): not a carrier operating only one CMV.
UPDATE compliancerules
   SET citation = '49 CFR 396.11(a)(1)-(a)(3), (a)(5); 49 CFR 396.13',
       description = 'A driver of a commercial motor vehicle reports on its condition at the end of the day''s work only where a defect or deficiency was found or reported to them (49 CFR 396.11(a)(2)(i)); no report is owed for a vehicle with nothing wrong. A defect likely to affect safe operation must be repaired, and the repair certified, before the vehicle is operated again (396.11(a)(3)) - that is what stops a vehicle here. A carrier operating only one commercial motor vehicle is not reached (396.11(a)(5)). A state''s own daily pre-trip inspection is a separate rule.'
 WHERE code = 'DVIR' AND accountid IS NULL AND effectiveto IS NULL;

-- The 90 days of DCH 916.2 is not applied (346); the descriptions said it was.
UPDATE compliancerules
   SET description = REPLACE(description,
         'A driver who has not had it has ninety days from assignment (916.2).',
         'It is required before driving: DCH 916.2 allows ninety days from assignment for a driver never trained before, which is not applied until the broker confirms in writing what it covers.')
 WHERE accountid IS NULL AND effectiveto IS NULL
   AND code IN ('GA_NET_FIRST_AID', 'GA_NET_SPILL_KIT', 'GA_NET_SAFETY_SENSITIVITY');
UPDATE compliancerules
   SET description = REPLACE(description,
         'a driver who has not had it has ninety days from assignment (916.2).',
         'it is required before driving - DCH 916.2 allows ninety days from assignment for a driver never trained before, which is not applied until the broker confirms in writing what it covers.')
 WHERE code = 'GA_NET_DRIVER_TRAINING' AND accountid IS NULL AND effectiveto IS NULL;

-- A company's own screening standard asks for a satisfactory result, not a completed check: a
-- report, a drug screen or a registry search counts once somebody has read what it says (a drug
-- screen also only when its result is recorded negative).
UPDATE compliancerules SET reviewrequired = 1
 WHERE accountid IS NULL AND effectiveto IS NULL
   AND code IN ('BACKGROUND_SCREENING', 'NONDOT_DRUG_SCREEN', 'ABUSE_REGISTRY_CHECK');
