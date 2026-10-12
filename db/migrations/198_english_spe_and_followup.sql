-- ################################################################################################
-- # 198 - three more a driver qualification file is supposed to establish.
-- #
-- #  ENGLISH PROFICIENCY - 391.11(b)(2). The carrier makes the determination; there is no
-- #  certificate to collect and nobody else to ask. So it is a field on the driver record with
-- #  three answers, and the third one matters: a driver nobody has assessed is not a driver who
-- #  passed. Same shape as the age rule - a requirement answered by something known rather than
-- #  by a document.
-- #
-- #  SPE CERTIFICATE - 391.49, and 391.51(b)(8) which wants a copy in the file. Where the driving
-- #  record says the driver holds a Skill Performance Evaluation certificate, the certificate
-- #  itself has to be here, and it has its own expiry independent of the medical card. A driver
-- #  with a current card and a lapsed SPE is not medically qualified, and until now nothing said so.
-- #
-- #  FOLLOW-UP TESTING - 40.307 and 382.311. A SAP who returns a driver to duty prescribes a
-- #  schedule of follow-up tests, at least six in the first twelve months. The plan has been stored
-- #  since the return-to-duty work went in and nothing ever asked for the tests.
-- ################################################################################################

ALTER TABLE drivers
  ADD COLUMN englishproficient TINYINT(1) NULL AFTER endorsementsneeded;

-- A credential type for the certificate, so it carries a document and an expiry of its own.
INSERT INTO credentialtypes (recordid, code, name, subject, description, active)
VALUES (UUID(), 'SPE_CERTIFICATE', 'Skill Performance Evaluation certificate', 'driver',
        'FMCSA certificate under 49 CFR 391.49 for a driver with a fixed deficit of a limb.', 1)
ON DUPLICATE KEY UPDATE active = 1;

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype, authority,
                             citation, applieswhen, evidencekind, evidencesource, origin,
                             extendable, extendnote, reviewrequired, determination, blocking, gate,
                             grouping, duestage, duetext, recurrence, warndays, note, sortorder,
                             effectivefrom)
VALUES
 (UUID(), 'driver', 'ENGLISH_PROFICIENCY', 'Able to read and speak English',
  'The driver must be able to read and speak English well enough to converse with the public, '
  'understand highway traffic signs and signals, respond to official inquiries, and make entries '
  'on reports and records. The carrier makes this determination - there is no certificate to '
  'collect - so it is recorded on the driver''s information page.',
  'regulation', 'FMCSA', '49 CFR 391.11(b)(2)',
  '{"all":[{"fact":"operation.interstate","is":true},{"fact":"driver.cmv","is":true}]}',
  'fact', 'driverfact:driver.english', 'office', 0,
  'A determination the carrier makes about a driver it is required to make it about.',
  0, 1, 1, 'hardstop', 'regulatory', 'prehire', NULL, 'once', 30, NULL, 6, CURRENT_DATE),

 (UUID(), 'driver', 'SPE_CERTIFICATE', 'Skill Performance Evaluation certificate',
  'The driving record shows this driver holds an SPE certificate - FMCSA''s permission to drive '
  'with a fixed deficit of a limb. 49 CFR 391.51(b)(8) requires a copy in the driver '
  'qualification file. It has its own expiry, and it is limited to the kind of vehicle the driver '
  'was evaluated in.',
  'regulation', 'FMCSA', '49 CFR 391.49; 49 CFR 391.51(b)(8)',
  '{"fact":"driver.spevariance","is":true}',
  'document', 'credential:SPE_CERTIFICATE', 'thirdparty', 0,
  'It applies to the drivers who hold one. There is nobody else to ask it of.',
  0, 0, 1, 'hardstop', 'regulatory', 'predrive', NULL, 'ondocument', 30, NULL, 17, CURRENT_DATE),

 (UUID(), 'driver', 'FOLLOWUP_TESTING', 'Follow-up testing after return to duty',
  'The substance abuse professional who returned this driver to duty prescribed a schedule of '
  'unannounced follow-up tests - at least six in the first twelve months. They are directly '
  'observed collections and they are the company''s obligation, not the driver''s.',
  'regulation', 'FMCSA', '49 CFR 40.307; 49 CFR 382.311',
  '{"fact":"driver.followupowed","is":true}',
  'test', 'drugtest:followup', 'thirdparty', 0,
  'Follow-up testing follows a SAP''s plan, not a company''s choice.',
  0, 1, 1, 'hardstop', 'regulatory', 'ongoing', 'On the schedule the SAP prescribed',
  'once', 30, NULL, 215, CURRENT_DATE);
