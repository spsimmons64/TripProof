-- What was done about a problem, as a thing that can be counted.
--
-- `tripissues.resolution` is free text, and free text cannot answer the question an operator
-- actually has at the end of a month: how many times did a vehicle have to come off the road, and
-- how many times did somebody else have to drive the trip. Those are the facts that decide whether
-- a van is worth keeping and whether the roster has enough slack in it.
--
-- So the WHAT becomes a chosen value and the free text stays beside it as the detail. The same
-- shape the product already uses for a cancellation reason and a broker rejection reason: chosen,
-- never typed, because a reason nobody can report on is a reason nobody will read.
ALTER TABLE tripissues ADD COLUMN IF NOT EXISTS resolutionkind VARCHAR(32) NULL AFTER resolvedby;

ALTER TABLE tripissues DROP CONSTRAINT IF EXISTS ck_tripissues_resolutionkind;
ALTER TABLE tripissues ADD CONSTRAINT ck_tripissues_resolutionkind CHECK (
  resolutionkind IS NULL OR resolutionkind IN (
    'carriedon', 'vehicleoff', 'vehiclechanged', 'driverchanged', 'cancelled',
    'passengertold', 'nothing', 'other'));
