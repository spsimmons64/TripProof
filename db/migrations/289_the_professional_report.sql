-- The Professional report, as backgroundchecks.com actually sells it.
--
-- 287 and 288 described the tiers from their add-on fields, which is how a report is bought ON TOP
-- of a package. What they actually sell is four named packages - Basic, County, Complete and
-- Professional - and the add-ons sit above those. This is the fourth tier, at the price TripProof
-- charges for it, with the vendor's own description of what it covers.

INSERT INTO feeschedule (recordid, code, name, covers, price, active, sortorder)
SELECT UUID(), 'BACKGROUND_PROFESSIONAL', 'Professional Background Check',
       'SSN trace, watchlists, national and seven-year county criminal searches, and education '
       'and employment verifications.',
       83.99, 1, 8
 WHERE NOT EXISTS (SELECT 1 FROM feeschedule WHERE code = 'BACKGROUND_PROFESSIONAL');
