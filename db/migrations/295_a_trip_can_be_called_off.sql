-- A trip can be called off, and the record says who called it off and why.
--
-- `triplegs.outcomestate` could already hold 'cancelled' and nothing could put it there: there was
-- no way to cancel a trip at all. A dispatcher whose passenger rings to say they no longer need
-- Thursday had the choice of leaving a trip on the board that will never be driven, or deleting
-- it - and deleting it loses the fact that it was ever booked, which is the thing a broker asks
-- about when it appears on their reconciliation.
--
-- So it is marked, not removed. The reason is chosen from a list because "cancelled" on its own
-- cannot be billed, disputed or reported on: a passenger who cancelled an hour before is a
-- different event from a facility that cancelled last week, and some contracts pay for one.

ALTER TABLE trips ADD COLUMN IF NOT EXISTS cancelreason VARCHAR(32) NULL;
ALTER TABLE trips ADD COLUMN IF NOT EXISTS cancelnote   VARCHAR(400) NULL;
ALTER TABLE trips ADD COLUMN IF NOT EXISTS cancelledon  DATETIME NULL;
ALTER TABLE trips ADD COLUMN IF NOT EXISTS cancelledby  VARCHAR(36) NULL;
