-- ################################################################################################
-- # 173 - the consent, named for the queries it actually covers.
-- #
-- # "Consent for Clearinghouse Query" reads as consent for any query. It is not: 49 CFR 382.703(a)
-- # consent covers LIMITED queries, and a full query needs the driver's own electronic consent
-- # given inside the Clearinghouse itself. The name now says which, so the caveat under it is
-- # confirming the title rather than correcting it.
-- ################################################################################################

UPDATE compliancerules
   SET name = 'Clearinghouse Limited Query General Consent'
 WHERE subject = 'driver' AND code = 'CLEARINGHOUSE_CONSENT' AND effectiveto IS NULL;
