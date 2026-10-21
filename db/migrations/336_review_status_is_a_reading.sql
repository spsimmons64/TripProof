-- ################################################################################################
-- # 336 - "approved" means somebody read the rule.
-- #
-- # On 2026-10-21 at 13:53 every rule in force was marked approved at once, so the trip check could
-- # be tried out - not because anybody had read them. All 123 had been drafts before it (the rule
-- # history says so). They go back to draft, and the reviewer and date the bulk approval stamped on
-- # them are cleared: approval is given in Rule Review, one rule at a time, by the person who read it.
-- #
-- # Only an approved rule may refuse a trip assignment. Until rules are approved again, the trip
-- # check refuses only on what is not a rule - a driver not hired, not approved for a contract, a
-- # vehicle without the lift a service needs - and records everything else.
-- ################################################################################################

UPDATE compliancerules
   SET legalreview = 'draft', legalreviewedby = NULL, legalreviewedon = NULL
 WHERE effectiveto IS NULL AND legalreview = 'approved'
   AND legalreviewedby = '0d11b211-b921-42d0-808a-2ac5d60768ce'
   AND legalreviewedon >= '2026-10-21 13:53:00' AND legalreviewedon < '2026-10-21 13:54:00';
