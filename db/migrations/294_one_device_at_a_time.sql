-- A driver is signed in on one device at a time.
--
-- Signing in somewhere new ends every other session. The reason is not tidiness: a phone left in a
-- vehicle at the end of a shift is a signed-in phone, and the next person to pick it up can see
-- another driver's work, report positions as them, and complete trips in their name. The record
-- would say that driver did it, and the record is what this product sells.
--
-- Done with a session id on the driver rather than a table of sessions: there is only ever one
-- live session, so the thing to store is which one. Every token carries it, and a token quoting
-- an id that is no longer the current one is simply not accepted.

ALTER TABLE drivers ADD COLUMN IF NOT EXISTS sessionid VARCHAR(36) NULL;
