-- A trip remembers which fee schedule priced it.
--
-- `billedamount` was written as zero on every hand-booked trip, with a comment saying a fee
-- schedule did not exist yet to work it out. One does now. But recording the figure is only half
-- of it: a schedule is superseded, retired and replaced, and a price recomputed next year from
-- whatever card is live then is not the price this trip was agreed at.
--
-- So the schedule is named on the trip. "What were we charging in March" stops being a question
-- about which card happened to be in force and becomes a fact on the record.
ALTER TABLE trips ADD COLUMN IF NOT EXISTS scheduleid VARCHAR(36) NULL AFTER billingstatus;
