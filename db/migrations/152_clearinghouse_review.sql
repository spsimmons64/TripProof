-- ################################################################################################
-- # 152 - a Clearinghouse query is read before it counts.
-- #
-- # The query comes back saying one of two things, and which one it says decides whether the driver
-- # may drive at all (49 CFR 382.701(a)). That is not a fact TripProof can read off the document -
-- # somebody in the office opens the query result and determines it, exactly as somebody reads a
-- # driving record and determines whether the driver is qualified.
-- #
-- # So the query follows the driving record's shape: sent for, received, read, and only then
-- # answered. Until somebody has read it, it is on file and unreviewed, which is its own state and
-- # is not compliance.
-- ################################################################################################

UPDATE compliancerules
   SET reviewrequired = 1
 WHERE subject = 'driver' AND code = 'CLEARINGHOUSE_PREEMP' AND effectiveto IS NULL;
