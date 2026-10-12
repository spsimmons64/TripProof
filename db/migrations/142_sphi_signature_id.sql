-- ################################################################################################
-- # 142 - which signature on file signed the request.
-- #
-- # The signature was being kept as a typed name and a hand, which draws the right picture and
-- # proves nothing. An office user has a signature of record here, adopted once behind a date of
-- # birth and a Social Security number and used for everything they sign - so what belongs on the
-- # request is a reference to THAT, the way every other signed thing in this system references it.
-- #
-- # The typed name and hand stay beside it: they are how it is drawn, and a signature that is later
-- # superseded must still print on an old request exactly as it printed the day it was signed.
-- ################################################################################################

ALTER TABLE employerinquiries
    ADD COLUMN IF NOT EXISTS requestsignatureid VARCHAR(36) NULL AFTER requestsignature;
