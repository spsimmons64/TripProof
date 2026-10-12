-- ################################################################################################
-- # 226 - empty an inbox that could never be emptied.
-- #
-- # `read_arrivals` matched the arrival's own word for a thing against the REQUIREMENT's code:
-- # DOT_MEDICAL_CARD against MEDICAL_CERT, PHI_ACK against PHI_CONFIDENTIALITY, DRIVER_LICENSE
-- # against DRIVER_LICENSE_COPY, SAFETY_PERFORMANCE against SAFETY_PERFORMANCE_HISTORY. Two
-- # vocabularies for one thing, so the match never succeeded and every document anybody read stayed
-- # in the dashboard queue for ever - including seven copies of one acknowledgment signed seven
-- # times.
-- #
-- # The matching is gone: the application now asks the engine whether the subject still has
-- # anything waiting on a reading, which is the only question that was ever being asked. This
-- # clears what the old way left behind.
-- #
-- # The rows are kept with a date rather than deleted - an arrival is a record that something came
-- # in, and that remains true whoever has since read it. What the engine still wants read will
-- # reappear from the engine, not from here.
-- ################################################################################################

UPDATE arriveddocuments
   SET reviewedon = UTC_TIMESTAMP()
 WHERE reviewedon IS NULL;
