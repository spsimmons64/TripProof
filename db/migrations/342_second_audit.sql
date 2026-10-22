-- ################################################################################################
-- # 342 - from the second audit of the rule export (2026-10-22).
-- ################################################################################################

-- The consent every driver signs (app/legal/driver/CLEARINGHOUSE_CONSENT.html) authorises limited
-- queries "for the duration of my employment", as 49 CFR 382.703(a) allows. Asking for it again
-- every twelve months asked for something the signed form already gives. Once for each hire.
UPDATE compliancerules SET recurrence = 'perhire', recurrencedays = NULL, recurrencemonths = NULL
 WHERE code = 'CLEARINGHOUSE_CONSENT' AND accountid IS NULL AND effectiveto IS NULL;

-- 49 CFR 391.33 accepts a CDL in place of the road test. A class letter alone does not say CDL:
-- Georgia's ordinary license is Class C. The license copy now stands in only for a driver whose
-- work calls for a CDL - the license rule already holds them to a CDL class.
UPDATE compliancerules
   SET alternatewhen = '{"all":[{"fact":"driver.cdl","is":true},{"fact":"driver.licenseclass","in":["A","B","C"]}]}'
 WHERE code = 'ROAD_TEST' AND accountid IS NULL AND effectiveto IS NULL;
