-- Three tiers of background check, priced where every other thing TripProof sells is priced.
--
-- The screening tiers lived in Python - a TIERS dict in the vendor's own module, carrying the name
-- shown to a customer, the sentence describing what it covers, and the price in cents. Changing
-- what a background check costs meant a deploy, and the price list the admin screen shows had a
-- row called "Background Check" with no price against it, because the real figures were somewhere
-- else. One thing, in two places, and only one of them was true.
--
-- A tier is now an ordinary fee schedule row. Two columns are added for what a price list does not
-- normally carry:
--
--   covers    the sentence the customer reads when choosing. Ours, not the vendor's.
--   products  what the vendor is asked for, as the vendor's own codes. The depth is ours to name
--             and sell; which searches that depth means is theirs to name.
--
-- `products` is deliberately left EMPTY. backgroundchecks.com publishes the names of what it sells
-- but not the codes its API takes, and the reference that does is behind their login. An order for
-- a tier with no products set is refused, by name, rather than sent and silently wrong - see
-- app/backgroundchecks.py. Fill these in from their API reference and no deploy is needed.

ALTER TABLE feeschedule ADD COLUMN IF NOT EXISTS covers VARCHAR(400) NULL AFTER name;
ALTER TABLE feeschedule ADD COLUMN IF NOT EXISTS products VARCHAR(200) NULL AFTER covers;

-- The single priceless "Background Check" row becomes the first of the three. Updated rather than
-- replaced so that anything already pointing at it keeps pointing at something.
UPDATE feeschedule
   SET code = 'BACKGROUND_BASIC',
       name = 'Basic Background Check',
       covers = 'National criminal records, the sex offender registry, and a Social Security '
                'number trace with the address history it returns.',
       price = COALESCE(price, 23.99),
       sortorder = 5
 WHERE code = 'BACKGROUND';

INSERT INTO feeschedule (recordid, code, name, covers, price, active, sortorder)
SELECT UUID(), 'BACKGROUND_STANDARD', 'Standard Background Check',
       'Everything in Basic, plus a county criminal search over seven years in every county the '
       'trace returns, and the driver''s motor vehicle record.',
       39.99, 1, 6
 WHERE NOT EXISTS (SELECT 1 FROM feeschedule WHERE code = 'BACKGROUND_STANDARD');

INSERT INTO feeschedule (recordid, code, name, covers, price, active, sortorder)
SELECT UUID(), 'BACKGROUND_COMPLETE', 'Complete Background Check',
       'Everything in Standard, plus federal criminal and statewide criminal searches and '
       'employment verification.',
       59.99, 1, 7
 WHERE NOT EXISTS (SELECT 1 FROM feeschedule WHERE code = 'BACKGROUND_COMPLETE');

-- The prices above are the figures the Certn tiers carried, with the middle one set between them.
-- They are a starting point and not a quote: set the real ones in Admin, Fee Schedule.
