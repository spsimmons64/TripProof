-- A trip has places, and somebody in it.
--
-- `trips` was built around a broker file: an external id, a billed amount, a batch. That is
-- the right shape for work that arrives already priced, and the wrong shape for the office
-- booking a private pay job - which has no broker reference, no amount yet, and above all a
-- passenger and two addresses.
--
-- The addresses go on the LEG rather than the trip, because a trip can be a round journey and
-- the return leg is a different pair of places. Coordinates sit beside them so the dispatch
-- screen can work out who is nearest without geocoding the same address on every page load.

ALTER TABLE trips
  -- Who is being carried. Not a driver and not a user - a passenger has no login and no
  -- record of their own here, so the name on the booking is the name.
  ADD COLUMN IF NOT EXISTS passenger     VARCHAR(160) NULL,
  ADD COLUMN IF NOT EXISTS passengerphone VARCHAR(32) NULL,
  -- What the office is booking against. A null broker already means private pay; this says
  -- so out loud rather than leaving it to be inferred from an absence.
  ADD COLUMN IF NOT EXISTS payer         VARCHAR(16) NULL,
  ADD COLUMN IF NOT EXISTS note          VARCHAR(512) NULL,
  -- Who booked it, where a person did. Imported trips have nobody.
  ADD COLUMN IF NOT EXISTS bookedby      VARCHAR(36) NULL;

ALTER TABLE triplegs
  ADD COLUMN IF NOT EXISTS pickupplace   VARCHAR(255) NULL,
  ADD COLUMN IF NOT EXISTS pickuplat     DECIMAL(9,6) NULL,
  ADD COLUMN IF NOT EXISTS pickuplng     DECIMAL(9,6) NULL,
  ADD COLUMN IF NOT EXISTS dropoffplace  VARCHAR(255) NULL,
  ADD COLUMN IF NOT EXISTS dropofflat    DECIMAL(9,6) NULL,
  ADD COLUMN IF NOT EXISTS dropofflng    DECIMAL(9,6) NULL,
  -- What the passenger needs, which decides whether a vehicle will do at all.
  ADD COLUMN IF NOT EXISTS servicelevel  VARCHAR(16) NULL;

-- A booked trip is not yet a billed one. `billedamount` is required by the table and means
-- nothing until a rate has been applied, so a booking carries zero and the fee schedule work
-- - deferred until trips arrive - is what will fill it.
