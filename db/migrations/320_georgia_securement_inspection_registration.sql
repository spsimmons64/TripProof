-- ################################################################################################
-- # 320 - Georgia: the securement failure rule, the six-month vehicle inspection, provider
-- # registration, and 907.15 on the suspension rule.
-- #
-- # 907.16    one confirmed failure to secure a member's wheelchair removes the driver until they
-- #           are retrained. Incidents get a record of their own; the rule looks for securement
-- #           training dated after the latest confirmed one.
-- # 910.1-2   every vehicle inspected by the broker before entering service and every six months.
-- # 701.1.4   the provider registered or licensed where the law requires (DPS, county).
-- # 907.15    restates the five-year suspension bar, with the child-support reinstatement terms.
-- # All drafts.
-- ################################################################################################

UPDATE compliancerules SET citation = 'DCH NEMT Part II (October 2026), Sections 907.15, 914.2.4 and 1006.5.3'
 WHERE code = 'GA_NET_MVR' AND accountid IS NULL AND effectiveto IS NULL;

CREATE TABLE IF NOT EXISTS driversecurementincidents (
  recordid    VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid   VARCHAR(36)  NOT NULL,
  driverid    VARCHAR(36)  NOT NULL,
  occurredon  DATE         NOT NULL,
  confirmed   TINYINT(1)   NOT NULL DEFAULT 0,   -- only a confirmed failure removes the driver
  note        VARCHAR(512) NULL,
  enteredby   VARCHAR(36)  NULL,
  createdon   DATETIME     NOT NULL,
  withdrawn   DATETIME     NULL,
  KEY ix_driversecurementincidents (accountid, driverid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO qualificationcatalog (code, name, area, sortorder) VALUES
  ('DRV-014', 'Cleared after a wheelchair securement failure', 'licensing', 23);

INSERT IGNORE INTO credentialtypes (recordid, accountid, code, name, subject, maxagedays, requirestesting,
                                    defaultvaliddays, hasamount, category, description, added, active)
VALUES
  (UUID(), NULL, 'BROKER_VEHICLE_INSPECTION', 'Broker vehicle inspection', 'vehicle', NULL, 0, 183, 0,
   'inspection', NULL, UTC_TIMESTAMP(), 1),
  (UUID(), NULL, 'GA_PROVIDER_REGISTRATION', 'Georgia transportation provider registration', 'company',
   NULL, 0, NULL, 0, 'registration', NULL, UTC_TIMESTAMP(), 1);

INSERT INTO compliancerules (recordid, accountid, code, qualificationcode, name, description, templatedocumentid, subject, authoritytype, authoritycategory, authority, jurisdiction, citation, sourceurl, applieswhen, program, evidencekind, evidencesource, origin, extendable, extendnote, offered, alternatesource, alternatewhen, reviewrequired, determination, blocking, gate, enforcement, legalreview, grouping, duestage, duedays, duetext, recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule, effectivefrom, effectiveto, supersedes, note, sortorder, added, addedby)
SELECT UUID(), NULL, 'GA_NET_SECUREMENT_CLEARED', 'DRV-014', 'Retrained after a wheelchair securement failure (Georgia NEMT)', 'A driver with one confirmed failure to properly secure a member''s wheelchair is removed from service until documentation shows they have been trained in the use of securement devices. Answered by securement training dated after the incident.', templatedocumentid, subject, 'regulation', 'STATE_MEDICAID', 'Georgia DCH', 'GA', 'DCH NEMT Part II (October 2026), Section 907.16', NULL, '{"all":[{"any":[{"fact":"company.state","eq":"GA"},{"fact":"company.operatingstates","has":"GA"}]},{"fact":"company.medicaid","is":true}]}', 'medicaid', 'record', 'securementclear', 'office', 0, extendnote, 0, NULL, NULL, reviewrequired, determination, 1, 'hardstop', enforcement, 'draft', 'regulatory', 'ongoing', duedays, duetext, 'ondocument', scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule, '2026-10-01', NULL, NULL, NULL, sortorder, UTC_TIMESTAMP(), NULL
FROM compliancerules WHERE code = 'DRIVER_LICENSE' AND accountid IS NULL AND effectiveto IS NULL
  AND NOT EXISTS (SELECT 1 FROM compliancerules x WHERE x.code = 'GA_NET_SECUREMENT_CLEARED');

INSERT INTO compliancerules (recordid, accountid, code, qualificationcode, name, description, templatedocumentid, subject, authoritytype, authoritycategory, authority, jurisdiction, citation, sourceurl, applieswhen, program, evidencekind, evidencesource, origin, extendable, extendnote, offered, alternatesource, alternatewhen, reviewrequired, determination, blocking, gate, enforcement, legalreview, grouping, duestage, duedays, duetext, recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule, effectivefrom, effectiveto, supersedes, note, sortorder, added, addedby)
SELECT UUID(), NULL, 'GA_NET_VEHICLE_INSPECTION', NULL, 'Broker vehicle inspection every six months (Georgia NEMT)', 'Each vehicle passes the broker''s inspection no earlier than 60 days before entering service, and again no later than six months after the most recent inspection.', templatedocumentid, subject, 'regulation', 'STATE_MEDICAID', 'Georgia DCH', 'GA', 'DCH NEMT Part II (October 2026), Sections 910.1 and 910.2', NULL, '{"all":[{"any":[{"fact":"company.state","eq":"GA"},{"fact":"company.operatingstates","has":"GA"}]},{"fact":"company.medicaid","is":true}]}', 'medicaid', evidencekind, 'credential:BROKER_VEHICLE_INSPECTION', origin, 0, extendnote, 0, NULL, NULL, reviewrequired, determination, 1, 'hardstop', enforcement, 'draft', grouping, duestage, duedays, duetext, 'days', scheduled, 183, violationresets, warndays, sensitivity, retentionrule, '2026-10-01', NULL, NULL, NULL, sortorder, UTC_TIMESTAMP(), NULL
FROM compliancerules WHERE code = 'TRANSIT_VEHICLE_INSPECTION' AND accountid IS NULL AND effectiveto IS NULL
  AND NOT EXISTS (SELECT 1 FROM compliancerules x WHERE x.code = 'GA_NET_VEHICLE_INSPECTION');

INSERT INTO compliancerules (recordid, accountid, code, qualificationcode, name, description, templatedocumentid, subject, authoritytype, authoritycategory, authority, jurisdiction, citation, sourceurl, applieswhen, program, evidencekind, evidencesource, origin, extendable, extendnote, offered, alternatesource, alternatewhen, reviewrequired, determination, blocking, gate, enforcement, legalreview, grouping, duestage, duedays, duetext, recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule, effectivefrom, effectiveto, supersedes, note, sortorder, added, addedby)
SELECT UUID(), NULL, 'GA_NET_PROVIDER_REGISTRATION', NULL, 'Registered with the Georgia Department of Public Safety or county where required', 'A transportation provider is registered or licensed where required by law or the appropriate authority (the Georgia Department of Public Safety, county government) and keeps the registration active throughout its service agreement. Whether registration is required depends on the operation and the exceptions in O.C.G.A. 40-1-100.', templatedocumentid, subject, 'regulation', 'STATE_MEDICAID', 'Georgia DCH', 'GA', 'DCH NEMT Part II (October 2026), Section 701.1.4', NULL, '{"all":[{"any":[{"fact":"company.state","eq":"GA"},{"fact":"company.operatingstates","has":"GA"}]},{"fact":"company.medicaid","is":true}]}', 'medicaid', evidencekind, 'credential:GA_PROVIDER_REGISTRATION', origin, 0, extendnote, 0, NULL, NULL, reviewrequired, determination, blocking, gate, enforcement, 'draft', grouping, duestage, duedays, duetext, 'ondocument', scheduled, NULL, violationresets, warndays, sensitivity, retentionrule, '2026-10-01', NULL, NULL, NULL, sortorder, UTC_TIMESTAMP(), NULL
FROM compliancerules WHERE code = 'BBP_EXPOSURE_PLAN' AND accountid IS NULL AND effectiveto IS NULL
  AND NOT EXISTS (SELECT 1 FROM compliancerules x WHERE x.code = 'GA_NET_PROVIDER_REGISTRATION');
