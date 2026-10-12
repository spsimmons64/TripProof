-- ################################################################################################
-- # 216 - the last two pieces of the drug and alcohol program: trained supervisors, and the draw.
-- #
-- # 202 left both out on purpose and said why: neither is a document the company holds, so bending
-- # them into credentials would have put a filing cabinet where a fact belongs. They get records of
-- # their own here.
-- #
-- #   REASONABLE SUSPICION TRAINING - 49 CFR 382.603. Every person designated to decide whether a
-- #   driver must be tested on reasonable suspicion needs at least sixty minutes on alcohol misuse
-- #   and at least sixty minutes on controlled substances. It is training a NAMED PERSON completed,
-- #   so it is recorded against the supervisor appointment in `companyroles`, and the requirement
-- #   is answered only when every appointed supervisor has it. One trained supervisor and three
-- #   untrained ones is not a trained supervisory staff.
-- #
-- #   RANDOM SELECTIONS - 49 CFR 382.305. A draw with a date, a pool and a list. The minimum annual
-- #   rates are 50 percent of average driver positions for controlled substances and 10 percent for
-- #   alcohol, unchanged since 2020, and the selections must be spread reasonably through the year
-- #   rather than taken all at once in December. The rates are not written into the rule row because
-- #   FMCSA may revise them each year; they live in the application where they can be corrected for
-- #   every customer at once.
-- #
-- # Both reach whoever the Clearinghouse registration reaches - the employer of a driver subject to
-- # Part 382 - and the condition is COPIED from that rule rather than written out again, so the
-- # three cannot drift apart the way the Safety Manager drifted from the plan.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS supervisortraining (
    recordid        VARCHAR(36) NOT NULL,
    accountid       VARCHAR(36) NOT NULL,
    userid          VARCHAR(36) NOT NULL,      -- the person, who holds the supervisor appointment
    completedon     DATE        NOT NULL,
    alcoholminutes  INT         NULL,          -- 382.603 wants at least 60
    drugminutes     INT         NULL,          -- and at least 60
    provider        VARCHAR(160) NULL,
    documentid      VARCHAR(36) NULL,
    note            VARCHAR(512) NULL,
    addedby         VARCHAR(36) NULL,
    added           DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted         DATETIME    NULL,
    PRIMARY KEY (recordid),
    KEY ix_supervisortraining_person (accountid, userid, completedon),
    CONSTRAINT fk_supervisortraining_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS randomselections (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    drawnon      DATE         NOT NULL,
    testtype     VARCHAR(8)   NOT NULL,        -- drug | alcohol
    poolsize     INT          NULL,            -- driver positions the draw was made from
    selected     INT          NULL,            -- how many names came out
    performedby  VARCHAR(160) NULL,            -- the consortium, the TPA, or in-house
    documentid   VARCHAR(36)  NULL,            -- the selection list, where one is kept
    note         VARCHAR(512) NULL,
    addedby      VARCHAR(36)  NULL,
    added        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted      DATETIME     NULL,
    PRIMARY KEY (recordid),
    KEY ix_randomselections_account (accountid, drawnon),
    CONSTRAINT fk_randomselections_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype, authority,
                             citation, applieswhen, evidencekind, evidencesource, origin,
                             extendable, reviewrequired, determination, blocking, gate, grouping,
                             duestage, duetext, recurrence, recurrencedays, warndays, note,
                             sortorder, effectivefrom)
SELECT UUID(), 'company', 'SUPERVISOR_TRAINING',
       'Reasonable suspicion training for supervisors',
       'Every person designated to decide whether a driver must be tested on reasonable suspicion '
       'needs at least sixty minutes of training on alcohol misuse and at least sixty minutes on '
       'controlled substances. Without it nobody in this company may lawfully send a driver for a '
       'reasonable suspicion test. Recorded against the people appointed as supervisors, and '
       'answered only when every one of them has it.',
       'regulation', 'FMCSA', '49 CFR 382.603', plan.applieswhen,
       'person', 'supervisortraining', 'office', 0, 0, 0, 1, 'deficiency', 'regulatory',
       'ongoing', 'Before anybody determines reasonable suspicion', 'once', NULL, 30, NULL, 15,
       CURRENT_DATE
  FROM (SELECT applieswhen FROM compliancerules
         WHERE subject = 'company' AND code = 'CLEARINGHOUSE_REGISTRATION' AND effectiveto IS NULL
         LIMIT 1) AS plan
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules
                    WHERE subject = 'company' AND code = 'SUPERVISOR_TRAINING'
                      AND effectiveto IS NULL);

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype, authority,
                             citation, applieswhen, evidencekind, evidencesource, origin,
                             extendable, reviewrequired, determination, blocking, gate, grouping,
                             duestage, duetext, recurrence, recurrencedays, warndays, note,
                             sortorder, effectivefrom)
SELECT UUID(), 'company', 'RANDOM_SELECTIONS', 'Random testing selections',
       'Drivers must be selected for random testing by a scientifically valid method, at the '
       'minimum annual rates FMCSA sets, with the selections spread reasonably through the year. '
       'The driver side of this is tracked on each driver''s own file - whether they are in the '
       'pool - and this is the other half: the draws themselves, with the date, the pool and who '
       'made them.',
       'regulation', 'FMCSA', '49 CFR 382.305', plan.applieswhen,
       'process', 'randomselections', 'office', 0, 0, 0, 1, 'deficiency', 'regulatory',
       'ongoing', 'Spread reasonably through the year', 'days', 365, 60, NULL, 16, CURRENT_DATE
  FROM (SELECT applieswhen FROM compliancerules
         WHERE subject = 'company' AND code = 'CLEARINGHOUSE_REGISTRATION' AND effectiveto IS NULL
         LIMIT 1) AS plan
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules
                    WHERE subject = 'company' AND code = 'RANDOM_SELECTIONS'
                      AND effectiveto IS NULL);
