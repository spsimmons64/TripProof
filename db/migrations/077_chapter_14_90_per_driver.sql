-- ################################################################################################
-- # 077 - the Chapter 14-90 requirements follow the driver's own switch.
-- #
-- # They were seeded off, because nothing could say whether the rule reached a company. Each driver
-- # now answers it: "operating covered busses in accordance with F.A.C. Chapter 14-90". So the four
-- # requirements are turned on, and the switch is what decides who they reach - an account that has
-- # deliberately set one of them since is left exactly as it set it.
-- ################################################################################################
UPDATE accountqualifications q
  JOIN compliancedocs c ON c.code = q.code AND c.subject = q.subject
   SET q.applies = 'both'
 WHERE q.subject = 'driver' AND q.applies = 'off' AND q.updated IS NULL
   AND c.sourcecode = 'FL_14_90';
