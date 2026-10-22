-- ################################################################################################
-- # 338 - the Georgia at-fault count and securement clearance do not expire.
-- #
-- # Both are worked out afresh from the driver's records every time they are read - the at-fault
-- # count from the driving records (DCH 914.2.5), the clearance from the securement incident record
-- # (DCH 907.16). Neither is a document with a life. They were written (318) with
-- # recurrence = 'ondocument', "renewed when the document on file expires", which put them on the
-- # driver's Validity-Tracked Documents panel reading "Nothing on file".
-- ################################################################################################

UPDATE compliancerules SET recurrence = 'once', recurrencedays = NULL
 WHERE code IN ('GA_NET_ATFAULT', 'GA_NET_SECUREMENT_CLEARED')
   AND accountid IS NULL AND effectiveto IS NULL;
