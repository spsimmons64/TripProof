-- A charge has a name, and mileage says which miles it counts.
--
-- Two gaps the first real schedule found.
--
-- NAME. A private-pay schedule carries six charges that are all `surcharge`: same-day
-- booking, after-hours, weekend, holiday, an extra attendant, a late cancellation. Held by
-- type alone they are six identical rows, indistinguishable in the grid and unreadable on an
-- invoice. The alternative was a rate type per charge, which puts the next contract's
-- invention behind a code change - exactly what rates-as-rows was built to avoid. So the
-- type stays small and the name is free text, written by whoever holds the contract.
--
-- LOADEDONLY. Mileage is charged on loaded miles - the ones with the passenger aboard. The
-- run out to collect somebody is deadhead and most schedules do not pay for it. `triplegs`
-- has recorded `loaded` since 270; until now the rate had no way to say it cared, so a
-- mileage rate would have billed the collection run too. Nullable rather than defaulted,
-- because it means nothing on a base fare or a no-show and a 0 there would read as a
-- deliberate "no, total miles".

ALTER TABLE payerrates
  ADD COLUMN IF NOT EXISTS name       VARCHAR(80) NULL AFTER ratetype,
  ADD COLUMN IF NOT EXISTS loadedonly TINYINT(1)  NULL;
