-- ################################################################################################
-- # 169 - the good faith effort keeps its own document.
-- #
-- # The effort lived as columns on the inquiry: a status, a note, a signature and a date. That is
-- # enough to drive a screen and not enough to hand anybody. 391.23(i) asks what was done, and the
-- # answer is a page - who was asked, every attempt, how it ended, signed - which is exactly what
-- # the SPHI reply already keeps for the other outcome.
-- #
-- # Drawn when it is certified, from what was on screen at that moment, so what is filed is what
-- # somebody signed rather than a page rebuilt later from columns that may have moved.
-- ################################################################################################

ALTER TABLE employerinquiries
    ADD COLUMN IF NOT EXISTS effortdocumentid VARCHAR(36) NULL AFTER effortsupersededon;
