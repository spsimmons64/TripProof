-- ################################################################################################
-- # 118 - an inquiry that came back empty is still an inquiry.
-- #
-- # Some licensing authorities return nothing. 49 CFR 391.23 is met in that case by documenting the
-- # good-faith effort and that no record was available - so the absence has to be recordable, or a
-- # state that genuinely has nothing to give sits in the file forever looking like a gap nobody
-- # chased.
-- #
-- # It is a flag on the inquiry rather than a separate kind of thing, because that is what it is:
-- # the request was made, the state answered, the answer was "nothing".
-- ################################################################################################
ALTER TABLE drivermvrs
    ADD COLUMN IF NOT EXISTS norecord TINYINT(1) NOT NULL DEFAULT 0 AFTER documentid;
