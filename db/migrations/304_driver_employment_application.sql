-- "DOT application for employment" becomes "Driver Employment Application".
--
-- The old name led with DOT, and DOT is the part that is least true of it for most of the drivers
-- this product carries: a non-CDL NEMT driver is not operating under 49 CFR 391 at all, and the
-- application is asked for by brokers and by the company's own policy. Naming it after an agency
-- that may not be involved tells an office the wrong thing about why it is on the list.
--
-- The code is untouched. EMPLOYMENT_APPLICATION is what every record, every evidence row and
-- every piece of code refers to; renaming that to tidy a label would be changing the thing to
-- suit the word for it.
UPDATE compliancerules
   SET name = 'Driver Employment Application'
 WHERE code = 'EMPLOYMENT_APPLICATION' AND effectiveto IS NULL;
