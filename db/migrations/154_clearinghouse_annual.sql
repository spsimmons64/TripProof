-- ################################################################################################
-- # 154 - a Clearinghouse query is good for a year.
-- #
-- # 49 CFR 382.701(b) requires a query at least once every twelve months, and the pre-employment
-- # full query answers that obligation for the year it is run in. Recording it as "once per hire"
-- # made it a thing that never went out of date, so a query run the week somebody was taken on
-- # still read as current three years later.
-- #
-- # Making it recur on days means the engine works the expiry out from the day the query was run,
-- # and every screen that shows the record gets the same date from the same arithmetic rather than
-- # each one adding a year of its own.
-- ################################################################################################

UPDATE compliancerules
   SET recurrence = 'days', recurrencedays = 365
 WHERE subject = 'driver' AND code = 'CLEARINGHOUSE_PREEMP' AND effectiveto IS NULL;
