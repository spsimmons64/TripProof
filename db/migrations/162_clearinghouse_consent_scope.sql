-- ################################################################################################
-- # 162 - what the consent on file actually covers.
-- #
-- # 49 CFR 382.703(a) consent is the general one: it lets the employer run LIMITED queries, which
-- # return only whether information exists about the driver. A FULL query - the one that returns
-- # what the information is, and the one run before hiring - needs the driver's own electronic
-- # consent given inside the FMCSA Clearinghouse, which this office cannot collect and TripProof
-- # cannot hold.
-- #
-- # Somebody reading a green tick beside "Consent for Clearinghouse Query" could reasonably think
-- # they were clear to run anything. They are not, and the file should say so where they are
-- # looking rather than in training somebody half remembers.
-- ################################################################################################

UPDATE compliancerules
   SET note = 'General consent for Clearinghouse limited queries. Does not replace the driver''s '
              'electronic consent in the FMCSA Clearinghouse for a full query.'
 WHERE subject = 'driver' AND code = 'CLEARINGHOUSE_CONSENT' AND effectiveto IS NULL;
