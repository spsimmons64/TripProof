-- ################################################################################################
-- # 221 - remove a note that explained nothing.
-- #
-- # 217 filled `extendnote` on the eight offered requirements with "Already a company requirement.
-- # Adopting it is how it reaches anybody at all." That field exists for one job, set out in 194:
-- # the caveat that comes with adopting a REGULATION beyond its reach - that a driving record
-- # obtained on a Class E driver is not a 49 CFR 391.23 record, that the Clearinghouse holds no
-- # entry for a driver without a CDL. A caveat about an obligation changing character on the way
-- # across.
-- #
-- # None of that applies to a requirement that is not a regulation. Nothing changes character,
-- # because nothing was a regulation to begin with. So the sentence appeared on screen as a warning
-- # about something, said nothing, and left the reader working out what it was warning them of.
-- #
-- # The row already says what it is: the authority line reads "Broker and payer contracts" and the
-- # choice reads "Not asked" or "Every driver". The field goes back to empty, which is what it
-- # should have been.
-- ################################################################################################

UPDATE compliancerules
   SET extendnote = NULL
 WHERE subject = 'driver' AND offered = 1 AND effectiveto IS NULL
   AND extendnote = 'Already a company requirement. Adopting it is how it reaches anybody at all.';
