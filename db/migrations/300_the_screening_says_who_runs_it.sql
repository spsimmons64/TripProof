-- The background screening requirement still describes Certn.
--
-- The vendor changed to backgroundchecks.com, and the words on screen did not follow: the office
-- reads "ordered through Certn" above a dialog that orders from somebody else, and the two depths
-- it names - Core and Complete - are Certn's, not the four tiers this product now sells.
--
-- Naming a vendor at all is a choice worth keeping. Which depth was bought is a fact an auditor
-- asks about, and a clear Basic search is not evidence that a Professional one would have come
-- back clear either. So the sentence stays and the names in it are put right.
UPDATE compliancerules
   SET description =
       'A criminal history and sex offender registry search on the driver, ordered through '
       'backgroundchecks.com. Basic covers national criminal records, the sex offender registry '
       'and a Social Security number trace; the wider tiers add county, federal and statewide '
       'criminal searches, the driving record, and employment and education verification. Not a '
       'federal requirement for a non-CDL driver - brokers and payers ask for it, and which depth '
       'they ask for is in the contract. The file records which was ordered, because a Basic '
       'search coming back clear is not evidence that a Professional one would have.'
 WHERE subject = 'driver' AND code = 'BACKGROUND_SCREENING' AND effectiveto IS NULL
   AND description LIKE '%Certn%';
