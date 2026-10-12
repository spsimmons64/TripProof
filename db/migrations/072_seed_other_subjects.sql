-- ################################################################################################
-- # 072 - the vehicle and company catalog, finished and seeded.
-- #
-- # 061 and 063 classified the driver requirements and left the other two subjects as they were, so
-- # every vehicle and company row still had no classification and no `requiredfor`. The account's
-- # list takes `requiredfor` as NOT NULL, and 071 inserted with IGNORE - so all 47 of them were
-- # dropped without a word. Both columns are filled in here from what the catalog already says, and
-- # the rows are seeded again.
-- #
-- # 'requiredfor' is a driver's distinction - commercial or not - so for these it is simply 'both'.
-- ################################################################################################
UPDATE compliancedocs
   SET requiredfor = COALESCE(requiredfor, 'both'),
       classification = COALESCE(classification,
                                 CASE obligation
                                     WHEN 'required'    THEN 'required'
                                     WHEN 'conditional' THEN 'conditional'
                                     ELSE 'contractual' END)
 WHERE subject IN ('vehicle', 'company');

INSERT IGNORE INTO accountqualifications
    (recordid, accountid, subject, code, catalog, stage, applies, obligation, requiredfor, expires,
     validdays, sortorder)
SELECT UUID(), a.recordid, c.subject, c.code, 1, COALESCE(c.stage, 'prehire'),
       CASE WHEN c.classification = 'required' THEN 'both' ELSE 'off' END,
       c.obligation, COALESCE(c.requiredfor, 'both'), c.expires, c.validdays, c.sortorder
FROM accounts a
CROSS JOIN compliancedocs c
WHERE a.deleted IS NULL AND a.platform = 0 AND c.active = 1 AND c.subject IN ('vehicle', 'company');
