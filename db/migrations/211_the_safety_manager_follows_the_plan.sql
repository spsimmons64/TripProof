-- ################################################################################################
-- # 211 - the Safety Manager reaches whoever the plan reaches.
-- #
-- # 209 gave the Safety Manager the condition the SSPP had in 202 - Florida AND a transit contract
-- # - and 203 had already taken the state test off the plan for a reason that applies here word for
-- # word: the obligation follows the contract, not the mailing address. The transit question asks
-- # about a Community Transportation Coordinator, a continuous transit contract or FDOT funding,
-- # which is itself the Florida question; answering it yes is the statement that Chapter 14-90
-- # reaches you.
-- #
-- # So an operator registered outside Florida running Florida transit work was asked for the plan
-- # and not for the person who administers it. The plan names that person in section 5.2, in
-- # section 29 and in appendix A, so it printed blanks with nothing anywhere asking to fill them.
-- #
-- # A rule that administers another rule carries that rule's condition. Copied from the SSPP rather
-- # than written out again, so the next time one of them moves the other cannot be left behind.
-- ################################################################################################

UPDATE compliancerules AS r
  JOIN (SELECT applieswhen FROM compliancerules
         WHERE subject = 'company' AND code = 'SSPP' AND effectiveto IS NULL LIMIT 1) AS plan
   SET r.applieswhen = plan.applieswhen
 WHERE r.subject = 'company' AND r.code = 'SAFETY_MANAGER' AND r.effectiveto IS NULL;
