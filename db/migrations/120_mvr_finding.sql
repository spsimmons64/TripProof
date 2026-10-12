-- ################################################################################################
-- # 120 - reading a driving record ends in a determination, not just a tick.
-- #
-- # `reviewstate` only went pending -> reviewed, so the act of reading a record was recorded and
-- # what the reader CONCLUDED was not. That is the wrong half to keep. A record showing a
-- # disqualifying offence and one showing nothing both ended up marked "reviewed", and the file
-- # could not tell them apart.
-- #
-- # This is deliberately not the annual review's finding. 49 CFR 391.25 is one determination about
-- # one driver once every 12 months; this is the disposition of one record, whenever it arrives.
-- # An MVR ordered in June to check on somebody is read on its own and, if it disqualifies, takes
-- # effect at once - the driver does not stay qualified until the annual comes round.
-- #
-- #   qualified     nothing on it affects this driver's qualification
-- #   restricted    something on it limits what they may do, recorded in the note
-- #   disqualified  they may not drive - and that applies from the moment it is recorded
-- ################################################################################################
ALTER TABLE drivermvrs
    ADD COLUMN IF NOT EXISTS finding VARCHAR(16) NULL AFTER reviewstate;
