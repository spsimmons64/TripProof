-- A tier has to name something the vendor sells.
--
-- Migration 287 gave the fee schedule a `products` column holding invented names - "mvr_addon",
-- "federal_criminal_addon" - written from the column headings on a report row, before anybody had
-- seen how an order is actually placed. Their reference now settles it: an order is a `report_sku`
-- plus a set of Y/N flags, and the flags are called `mvr`, `employment`, `education`, `blj`,
-- `federal_criminal` and `drug_test`. A drug test also needs its own SKU, because they sell six
-- panels and there is no default.
--
-- So the tier gains the SKU it orders, and `products` becomes the flag list in the vendor's own
-- words rather than ours. One translation fewer between what is sold and what is bought.
--
-- The SKUs below are the ones this account actually has, read from GET /skus:
--   hire1      $24.99  Basic         national criminal, SSN trace, some watchlists
--   hire2      $34.99  County        the above plus one county criminal search
--   hire3      $39.99  Complete      the above plus a full seven-year county search
--   hire4emp1  $69.99  Professional  the above plus federal criminal, education, 1 employment
--   hire4emp7  $84.99  Professional with a seven-year employment history
ALTER TABLE feeschedule ADD COLUMN IF NOT EXISTS reportsku VARCHAR(32) NULL AFTER products;
ALTER TABLE feeschedule ADD COLUMN IF NOT EXISTS drugsku   VARCHAR(32) NULL AFTER reportsku;

UPDATE feeschedule SET reportsku = 'hire1',     products = NULL
 WHERE code = 'BACKGROUND_BASIC';
UPDATE feeschedule SET reportsku = 'hire3',     products = 'mvr'
 WHERE code = 'BACKGROUND_STANDARD';
UPDATE feeschedule SET reportsku = 'hire3',     products = 'mvr,federal_criminal,employment'
 WHERE code = 'BACKGROUND_COMPLETE';
-- hire4emp1 already carries federal criminal, education and one employment verification, so the
-- only thing bought on top is the driving record - which is the one this company cannot do
-- without.
UPDATE feeschedule SET reportsku = 'hire4emp1', products = 'mvr'
 WHERE code = 'BACKGROUND_PROFESSIONAL';
