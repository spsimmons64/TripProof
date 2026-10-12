-- ################################################################################################
-- # 168 - the 30-day window, and a reply that arrives after the effort was filed.
-- #
-- # THE WINDOW. 49 CFR 391.23(d) gives the carrier 30 days from the start of employment to obtain
-- # the safety performance history. After that the asking is late: a request sent on day 60 does
-- # not make the file compliant, and recording it as though it does hides the gap. So requests stop
-- # at hire plus 30 days, and what is left is to certify what was actually done inside the window.
-- #
-- # THE REPLY THAT ARRIVES LATE. A good faith effort says "we asked and nobody answered". If the
-- # employer then answers, that sentence is no longer true: the records are here and nobody in this
-- # office has read them. The reply must beat the effort - the requirement goes back to needing a
-- # review - and the effort stays on file as what was done, stamped with the day it was overtaken.
-- # Deleting it would lose the history; leaving it unmarked would let the file claim an effort was
-- # the ending when it was not.
-- ################################################################################################

ALTER TABLE employerinquiries
    ADD COLUMN IF NOT EXISTS effortsupersededon DATETIME NULL AFTER effortsignedon;
