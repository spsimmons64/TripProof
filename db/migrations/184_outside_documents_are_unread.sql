-- ################################################################################################
-- # 184 - anything from outside is unread until somebody here reads it. Once, for everything.
-- #
-- # This rule has been stated and broken repeatedly, and the reason is that it has never been
-- # written down anywhere the engine can see. It has lived as a habit applied case by case: the
-- # upload link got it, then the signing link, then the road test, then the MVR order - each one a
-- # separate patch, each one found by somebody noticing a green tick they had not earned.
-- #
-- # A habit applied per path is a habit that will be forgotten on the next path. So the fact moves
-- # onto the rule itself: `origin` says where the evidence for this requirement comes from, and the
-- # engine asks that one question instead of knowing about links, orders, labs and examiners.
-- #
-- #   outside   somebody other than this office produced it - a driver, a doctor, a laboratory, a
-- #             licensing authority, a previous employer, an examiner, a federal database. It may
-- #             be the wrong document, an expired one, or a photograph of something else, and it
-- #             does not stand until somebody here says they have read it.
-- #   inhouse   this office produced it. The annual review is a determination somebody here made,
-- #             and the random pool is this company's own record of its own programme. There is
-- #             nobody else to check after.
-- #
-- # `documentreads` is the other half: a single place saying "somebody here read this record", for
-- # the sources that have nowhere of their own to say it. Where a source already carries its own
-- # reading - an MVR's finding, a report's outcome, a road test's result - that still counts, and
-- # those flows are untouched.
-- ################################################################################################

ALTER TABLE compliancerules ADD COLUMN origin VARCHAR(8) NOT NULL DEFAULT 'outside' AFTER evidencesource;

-- The two things this office makes itself.
UPDATE compliancerules
   SET origin = 'inhouse'
 WHERE subject = 'driver'
   AND (evidencesource IS NULL OR evidencesource IN ('annualreview', 'poolmember'));

CREATE TABLE IF NOT EXISTS documentreads (
    recordid    VARCHAR(36)  NOT NULL,
    accountid   VARCHAR(36)  NOT NULL,
    subject     VARCHAR(8)   NOT NULL,      -- driver | vehicle | company
    subjectid   VARCHAR(36)  NOT NULL,
    sourcetable VARCHAR(32)  NOT NULL,      -- which table the record lives in
    sourceid    VARCHAR(36)  NOT NULL,      -- its recordid there
    readon      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    readby      VARCHAR(36)  NULL,
    note        VARCHAR(512) NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_documentreads_record (accountid, sourcetable, sourceid),
    KEY ix_documentreads_subject (accountid, subject, subjectid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Everything already on file was put there before this rule existed and has been looked at by
-- somebody working through these screens. Marking it all unread now would turn every driver in
-- every account red over work that was done - the rule starts from today.
INSERT INTO documentreads (recordid, accountid, subject, subjectid, sourcetable, sourceid, note)
SELECT UUID(), c.accountid, 'driver', c.subjectid, 'credentials', c.recordid,
       'On file before reading was recorded.'
  FROM credentials c
 WHERE c.subject = 'driver' AND c.deleted IS NULL AND c.revokedon IS NULL;

INSERT INTO documentreads (recordid, accountid, subject, subjectid, sourcetable, sourceid, note)
SELECT UUID(), accountid, 'driver', driverid, 'exclusionchecks', recordid,
       'On file before reading was recorded.'
  FROM exclusionchecks;

INSERT INTO documentreads (recordid, accountid, subject, subjectid, sourcetable, sourceid, note)
SELECT UUID(), accountid, 'driver', driverid, 'drugtests', recordid,
       'On file before reading was recorded.'
  FROM drugtests;

INSERT INTO documentreads (recordid, accountid, subject, subjectid, sourcetable, sourceid, note)
SELECT UUID(), accountid, 'driver', driverid, 'transitmedicals', recordid,
       'On file before reading was recorded.'
  FROM transitmedicals;
