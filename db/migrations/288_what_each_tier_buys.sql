-- What each tier actually buys, in the vendor's own field names.
--
-- 287 left `products` empty because the codes were not known. They are now, read off a real
-- report on the account: depth is bought with per-add-on fields - mvr_addon, blj_addon,
-- federal_criminal_addon, drug_addon, employment_addon, education_addon - on top of a base report
-- that already carries the national criminal search, the county search and the identity trace.
--
-- So a tier is a set of add-ons, and the cheapest tier has none. That is not a tier nobody
-- configured; it is the base report, which is a real thing to sell.

UPDATE feeschedule SET products = NULL
 WHERE code = 'BACKGROUND_BASIC';

UPDATE feeschedule SET products = 'mvr_addon'
 WHERE code = 'BACKGROUND_STANDARD';

UPDATE feeschedule SET products = 'mvr_addon, federal_criminal_addon, employment_addon'
 WHERE code = 'BACKGROUND_COMPLETE';
