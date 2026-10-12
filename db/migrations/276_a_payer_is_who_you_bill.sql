-- A payer is who you bill.
--
-- `billtoid` said "the money comes from this payer, but send the paperwork to that one". It
-- does not survive contact with how NEMT actually works. Either a company contracts directly
-- with a Medicare Advantage plan - in which case the plan is the payer, holds the rate sheet
-- and receives the claim - or the plan routes its transport through a broker, in which case
-- the company's contract, rates and money all come from the BROKER, and the plan is
-- commercially invisible to it. Both collapse to one party.
--
-- What the column was reaching for is real but belongs elsewhere: whose coverage the
-- PASSENGER has is trip-level, varies by passenger, and lives with the member data in the
-- PHI vault. It could never have sat on a fee schedule. And a payer whose claims go under
-- another name is already answered by `payers.payerid`, the clearinghouse's own identifier.
--
-- Dropped rather than left dormant. It held no data, and an unused column encoding a wrong
-- model is the thing somebody builds on in six months.

ALTER TABLE payerschedules DROP FOREIGN KEY IF EXISTS fk_payerschedules_billto;
ALTER TABLE payerschedules DROP COLUMN IF EXISTS billtoid;
