-- ################################################################################################
-- # 357 - a vehicle's insurance is a hard stop, not a paperwork deficiency.
-- #
-- # Carrying passengers for hire uninsured is unlawful in Florida and Georgia, and under 49 CFR
-- # 387 for interstate carriage. The trip check already refused a vehicle with none on file once
-- # the rule was approved; labelled a deficiency, the vehicle's own page and the dispatch list
-- # treated it as paperwork. Now every screen says the same thing the trip check does.
-- ################################################################################################

UPDATE compliancerules SET gate = 'hardstop'
 WHERE code = 'VEHICLE_INSURANCE_CARD' AND accountid IS NULL AND effectiveto IS NULL;
