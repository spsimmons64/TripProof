-- ################################################################################################
-- # 013 - a broker's rules can be a complete list: the state's rules imported when the broker was
-- # added to the state, then edited. includesbase = 1 marks such a version; for that broker's trips
-- # it replaces the state baseline instead of adding to it. Older broker versions (0) keep adding
-- # to the baseline, so results already given don't change.
-- #
-- # Pending changes to the Florida broker sets are brought into the new model here: they gain the
-- # Florida baseline's live requirements they don't already cover (same test / credential type).
-- ################################################################################################
ALTER TABLE rulesets ADD COLUMN IF NOT EXISTS includesbase TINYINT(1) NOT NULL DEFAULT 0 AFTER brokerid;

INSERT INTO requirements (recordid, rulesetid, code, kind, subject, credentialtypeid, maxagedays, gracedays,
                          servicelevels, params, description, citation, regulationid, sourceid)
SELECT UUID(), d.recordid, q.code, q.kind, q.subject, q.credentialtypeid, q.maxagedays, q.gracedays,
       q.servicelevels, q.params, q.description, q.citation, q.regulationid, q.sourceid
FROM rulesets d
JOIN rulesets b ON b.state = d.state AND b.brokerid IS NULL AND b.status = 'published'
                AND b.effectivefrom <= CURDATE() AND (b.effectiveto IS NULL OR b.effectiveto >= CURDATE())
JOIN requirements q ON q.rulesetid = b.recordid
WHERE d.brokerid IS NOT NULL AND d.status = 'draft' AND d.includesbase = 0
  AND NOT EXISTS (SELECT 1 FROM requirements x WHERE x.rulesetid = d.recordid
                  AND (x.code = q.code OR (x.kind = q.kind AND x.credentialtypeid <=> q.credentialtypeid)));

UPDATE rulesets SET includesbase = 1 WHERE brokerid IS NOT NULL AND status = 'draft';
