-- Two different things called "hours of service", separated.
--
-- FL_HOURS_OF_SERVICE is retired. What it was built to hold - a driver's ongoing duty record
-- under F.A.C. 14-90.006 - is a worthwhile thing to keep, and the store for it stays
-- (driverdutydays, app/hos.py, the Hours Of Service tab). But it is an operational log that
-- wants GPS and a driver app behind it to be worth anything, not a compliance requirement with
-- a document behind it, and sitting on the requirements list it only asked somebody to type in
-- what the vehicle already knows.
--
-- What IS a requirement, and what was missing, is the other one: the driver's statement of the
-- hours they had already worked BEFORE they got here.
--
-- 49 CFR 395.8(j)(2): before a driver begins work, the motor carrier must obtain from them a
-- signed statement of the total time on duty during the immediately preceding 7 days and the
-- time at which they were last relieved from duty. It exists because the hours limits follow
-- the PERSON, not the employer: a driver who worked 65 hours last week somewhere else does not
-- arrive with a clean sheet, and a carrier that dispatches them without asking has no way to
-- know how many hours it may lawfully use.
--
--   * ON DUTY, not driving. The statement is total on-duty time, which includes loading,
--     waiting, inspecting and anything else the driver was required to be doing.
--   * It covers work for ANY employer, not only transport work for this one.
--   * Once, before first dispatch - not annually. An intermittent driver gives one again when
--     they come back.
--   * Prior records of duty status or an ELD printout are acceptable instead of the form.

UPDATE compliancerules
   SET effectiveto = CURDATE(),
       note = 'Retired. The Chapter 14-90 duty log is kept as an operational record rather than '
              'as a requirement; the pre-dispatch obligation is PREV7_ONDUTY under 395.8(j)(2).'
 WHERE code = 'FL_HOURS_OF_SERVICE';

INSERT INTO compliancerules
  (recordid, accountid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, sourceurl, applieswhen, evidencekind, evidencesource, origin, extendable, blocking,
   gate, grouping, duestage, duetext, recurrence, warndays, sensitivity, retentionrule,
   effectivefrom, sortorder)
SELECT UUID(), NULL, 'PREV7_ONDUTY',
       'Statement of on-duty hours for the previous 7 days',
       CONCAT('Before a driver begins work, the carrier must obtain from them a signed ',
              'statement of the total time ON DUTY during the immediately preceding 7 days, ',
              'and the time at which they were last relieved from duty. On-duty time is not ',
              'just driving - it includes loading, waiting, inspecting and anything else they ',
              'were required to be doing - and it covers work for any employer, not only this ',
              'one. The limits follow the person: a driver who worked 65 hours last week ',
              'somewhere else does not arrive with a clean sheet. Prior records of duty status ',
              'or an ELD printout are acceptable in place of the statement.'),
       'driver', 'regulation', 'FMCSA', 'US', '49 CFR 395.8(j)(2)',
       'https://www.ecfr.gov/current/title-49/section-395.8',
       '{"all":[{"fact":"operation.interstate","is":true},{"fact":"driver.cmv","is":true}]}',
       'document', 'signature:PREV7_ONDUTY', 'thirdparty', 0, 1,
       'hardstop', 'regulatory', 'predrive',
       'Before the driver is first dispatched',
       'once', 30, 'normal',
       '6 months - 49 CFR 395.8(k)(1)', '1970-01-01', 235
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'PREV7_ONDUTY');
