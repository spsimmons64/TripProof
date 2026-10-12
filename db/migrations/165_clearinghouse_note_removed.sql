-- ################################################################################################
-- # 165 - the Clearinghouse consent caveat comes off the list.
-- #
-- # Nothing is wrong with what it said - a 382.703(a) consent really does not stand in for the
-- # driver's electronic consent to a full query - but a warning band on a row that is otherwise
-- # satisfied reads as a problem with the record, and it is not one.
-- #
-- # The mechanism stays: any rule may carry a `note` and the screen prints it under the citation.
-- # This one simply does not need to shout on a list that is read every day.
-- ################################################################################################

UPDATE compliancerules
   SET note = NULL
 WHERE subject = 'driver' AND code = 'CLEARINGHOUSE_CONSENT' AND effectiveto IS NULL;
