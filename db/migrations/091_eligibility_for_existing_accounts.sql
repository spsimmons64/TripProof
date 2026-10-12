-- ################################################################################################
-- # 091 - the eligibility check reaches accounts that already exist.
-- #
-- # An account's own rule set is rewritten from its qualification list whenever that list is
-- # touched, so a new rule would otherwise only reach a company on the day someone happened to
-- # change a setting. A bar on driving is not something to wait for: every account gets it now.
-- ################################################################################################
INSERT INTO requirements (recordid, rulesetid, code, kind, status, subject, gracedays, description,
                          legalcitation)
SELECT UUID(), r.recordid, 'DOT_ELIGIBILITY', 'eligibility', 'REQUIRED', 'driver', 0,
       'The driver is not prohibited from performing safety-sensitive functions',
       '49 CFR 382.501; 382.701'
  FROM rulesets r
 WHERE r.accountid IS NOT NULL AND r.level = 'account'
   AND NOT EXISTS (SELECT 1 FROM requirements q
                    WHERE q.rulesetid = r.recordid AND q.code = 'DOT_ELIGIBILITY');
