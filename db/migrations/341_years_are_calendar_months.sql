-- ################################################################################################
-- # 341 - a year is twelve calendar months, not 365 days.
-- #
-- # The sources say "every twelve months", "annually", "every two years", "monthly". Counted in
-- # days, each lands a day early whenever it crosses 29 February, and since 340 a record's own
-- # date cannot outlast the rule's interval - so a Florida transit medical printed good through
-- # 09/30/2028 showed as lapsing on 09/29/2028. Counted in calendar months it lands on the date the
-- # source means. Only the three-day SAM.gov sweep is a count of days, and stays one.
-- ################################################################################################

UPDATE compliancerules
   SET recurrence = 'months',
       recurrencemonths = CASE recurrencedays WHEN 31 THEN 1 WHEN 365 THEN 12 WHEN 730 THEN 24
                                              WHEN 1825 THEN 60 END,
       recurrencedays = NULL
 WHERE accountid IS NULL AND effectiveto IS NULL AND recurrence = 'days'
   AND recurrencedays IN (31, 365, 730, 1825);
