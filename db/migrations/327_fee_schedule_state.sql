-- ################################################################################################
-- # 327 - a fee schedule can be for one state.
-- #
-- # A company carrying for MTM in Florida and Georgia is paid two different rates. A schedule with a
-- # state prices only trips picked up there; one without covers every state, as before, and a
-- # state's own schedule wins over it.
-- ################################################################################################

ALTER TABLE payerschedules ADD COLUMN IF NOT EXISTS state CHAR(2) NULL AFTER payerkinds;
