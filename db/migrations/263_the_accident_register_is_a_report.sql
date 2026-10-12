-- The accident register comes off the requirements screen.
--
-- 49 CFR 390.15(b) still asks for the list to be kept, and it still is: every accident is
-- recorded against the driver it happened to, and the register is that set of rows read across
-- the roster. What changes is where it is read. A list of accidents is a report - something you
-- run, sort and hand over - not a thing that sits in a column of requirements saying "yes" with
-- a tick beside it, and showing it there put a standing green mark on a screen whose job is to
-- show what is outstanding.
--
-- Retired rather than deleted. The rule keeps its row with a date on it, which is how every
-- other rule that stops applying is handled, and nothing about the accidents themselves moves:
--
--   * driveraccidents keeps every row, withdrawn ones included.
--   * The Accident History tab on each driver still records and reads them.
--   * POSTACCIDENT_TEST still reads driver.postaccidentowed off the same rows, so an accident
--     that owes a test still stops that driver.
--   * GET /accidents still serves the whole register, which is what the report will read.
UPDATE compliancerules
   SET effectiveto = '2026-10-08'
 WHERE code = 'ACCIDENT_REGISTER' AND effectiveto IS NULL;
