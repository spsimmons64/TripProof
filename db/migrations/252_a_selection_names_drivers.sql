-- A random selection names drivers. It used to be a number.
--
-- 49 CFR 382.305. A draw recorded "3 came out" and nothing else, so the names existed only
-- inside whatever PDF somebody attached. That left the file unable to answer the question an
-- audit actually asks - which is not "did you draw three names" but "were those three drivers
-- tested, and promptly".
--
-- Everything downstream of the draw was therefore disconnected:
--
--   * A driver selected and never tested flagged nowhere, on either side.
--   * 382.305(l) says a notified driver proceeds to the collection site immediately. Nothing
--     recorded when they were told, so "promptly" could not be shown either way.
--   * A driver legitimately unavailable - on leave the week they came out - is allowed, but it
--     has to be RECORDED. An absence in the file is not a record of a reason.
--   * `selected` was typed in by hand, the same fault poolsize had: a number beside a list that
--     could have been counted.
--
-- Now one row per selected driver, carrying what happened to them.

CREATE TABLE IF NOT EXISTS randomselecteddrivers (
  recordid    varchar(36) NOT NULL,
  accountid   varchar(36) NOT NULL,
  selectionid varchar(36) NOT NULL,
  driverid    varchar(36) NOT NULL,
  -- 382.305(l). The moment the driver was told, which is when the clock on "immediately" starts.
  notifiedon  datetime    DEFAULT NULL,
  -- The test that answered this selection. NULL means it is still owed.
  testid      varchar(36) DEFAULT NULL,
  -- Why no test was done, where that is legitimate. A reason on the record is the difference
  -- between a driver who was on leave and a selection nobody followed up.
  excused     varchar(255) DEFAULT NULL,
  excusedon   date        DEFAULT NULL,
  addedby     varchar(36) DEFAULT NULL,
  added       datetime    NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (recordid),
  UNIQUE KEY ux_selected_once (selectionid, driverid),
  KEY ix_selected_driver (accountid, driverid, added),
  CONSTRAINT fk_selected_account   FOREIGN KEY (accountid)   REFERENCES accounts (recordid),
  CONSTRAINT fk_selected_selection FOREIGN KEY (selectionid) REFERENCES randomselections (recordid),
  CONSTRAINT fk_selected_driver    FOREIGN KEY (driverid)    REFERENCES drivers (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The test a selection is still waiting for.
--
-- Written exactly like POSTACCIDENT_TEST, because it is the same kind of thing: an obligation
-- that exists because an event happened, reaching the driver only while it is unanswered and
-- leaving their list the moment it is. It is answered by an ordinary random test on the driver's
-- own record - app/eligibility.py links one to the open selection when it is filed - so there is
-- no new screen and nothing new to learn.
--
-- A deficiency, not a hard stop. Being selected is not a bar: the driver is expected to go and
-- be tested, and stopping them the moment their name comes out would be the software inventing a
-- consequence the regulation does not impose. A driver who REFUSES is a different matter and is
-- already a hard stop - it is recorded as a test with a result of refusal, which prohibits them
-- under 382.211.
INSERT INTO compliancerules
  (recordid, accountid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, sourceurl, applieswhen, evidencekind, evidencesource, origin, extendable, blocking,
   gate, grouping, duestage, duetext, recurrence, warndays, sensitivity, retentionrule,
   effectivefrom, sortorder)
SELECT UUID(), NULL, 'RANDOM_TEST_OWED',
       'Test owed from a random selection',
       CONCAT('This driver''s name came out of the random testing pool and no test is on file ',
              'for it yet. 49 CFR 382.305(l): a driver notified of selection must proceed to ',
              'the collection site immediately, and the carrier must ensure the test is ',
              'completed. Where the driver genuinely could not be tested - away, on leave, no ',
              'longer driving - that is allowed, but the reason belongs on the record: an ',
              'absence in the file is not a record of a reason.'),
       'driver', 'regulation', 'FMCSA', 'US', '49 CFR 382.305(l)',
       'https://www.ecfr.gov/current/title-49/section-382.305',
       '{"fact":"driver.randomtestowed","is":true}',
       'test', 'drugtest:random', 'thirdparty', 0, 0,
       'deficiency', 'regulatory', 'ongoing',
       'Immediately on being notified of selection',
       'once', 0, 'normal',
       'Two years - 49 CFR 382.401(b)(1)(v)', '1970-01-01', 212
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'RANDOM_TEST_OWED');
