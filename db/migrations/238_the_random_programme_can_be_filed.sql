-- Make the random testing programme something the company can actually file.
--
-- 237 gave the rule a bespoke evidence source, `randomprogram`. The company requirements screen
-- knows how to file exactly one kind of thing - a credential - and dispatches on the source
-- name to decide what a requirement's Add button should do. An unrecognised source gets a
-- requirement that appears on the list, goes red, and has no way to be answered.
--
-- That is the second time in this session a rule has been added with nowhere to act on it. The
-- source is now an ordinary `credential:` one, which the existing screen already handles, and
-- the part that is NOT ordinary - that an enrolment with no draws behind it is not compliance -
-- stays in the engine where it belongs.

UPDATE compliancerules
   SET evidencesource = 'credential:RANDOM_TESTING_PROGRAM'
 WHERE code = 'RANDOM_TESTING_PROGRAM';

-- The SSPP recordkeeping rule is answered by the driver records themselves and has nothing to
-- upload, which is correct - but the screen must not offer an Add button that posts nothing.
-- `process` is the evidence kind the other answered-by-records rules use.
UPDATE compliancerules
   SET evidencekind = 'process'
 WHERE code = 'FL_SSPP_RECORDKEEPING';
