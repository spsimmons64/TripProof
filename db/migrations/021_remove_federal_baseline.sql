-- ################################################################################################
-- # 021 - remove the federal baseline loaded in 020; a different approach is coming.
-- #
-- # Goes: the US-FED rule set and its requirements, the trip checks made against them, the
-- # per-customer checklist (it only ever held US-FED obligations), and the credential type 020
-- # added for it. Evaluation runs stay, so existing audit packets still reference their run.
-- # Stays: credential vault, drivers, vehicles, trips, credential types, brokers, and the engine.
-- ################################################################################################
DELETE l FROM legchecks l
    JOIN requirements q ON q.recordid = l.requirementid
    JOIN rulesets r ON r.recordid = q.rulesetid
    WHERE r.family = 'US-FED';

DELETE q FROM requirements q JOIN rulesets r ON r.recordid = q.rulesetid WHERE r.family = 'US-FED';
DELETE FROM rulesets WHERE family = 'US-FED';

DROP TABLE IF EXISTS accountchecklist;

DELETE FROM credentialtypes WHERE code = 'DRUG_LAW_POLICY'
    AND NOT EXISTS (SELECT 1 FROM credentials c WHERE c.credentialtypeid = credentialtypes.recordid);
