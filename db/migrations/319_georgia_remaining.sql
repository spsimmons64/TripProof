-- ################################################################################################
-- # 319 - the rest of Georgia's NEMT requirements.
-- #
-- # 914.2.5   a driver convicted of two at-fault moving violations and/or accidents on NEMT work is
-- #           removed from service. The accident register learns whether the driver was at fault, and
-- #           moving violations get a record of their own; the rule counts the two together.
-- # 915.1.3   the provider has a process to address state drug law violations - company requirement.
-- # 915.1.4   the provider has a process to disclose drivers' driving history to Medicaid - company.
-- # 608.6/.8  the broker may not contract with a provider whose owners are excluded - so the
-- #           company screens its owners and managing employees monthly.
-- # 608.7     the Death Master File check of drivers is the broker's duty; offered, for a company
-- #           whose broker passes it down.
-- #
-- # Not built, and not to be: 803 (volunteer drivers the broker arranges) and 804 (ride-share
-- # companies) describe neither a transportation provider nor its drivers.
-- # All drafts.
-- ################################################################################################

ALTER TABLE driveraccidents ADD COLUMN IF NOT EXISTS atfault TINYINT(1) NULL AFTER citedon;

CREATE TABLE IF NOT EXISTS drivermovingviolations (
  recordid    VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid   VARCHAR(36)  NOT NULL,
  driverid    VARCHAR(36)  NOT NULL,
  occurredon  DATE         NOT NULL,
  violation   VARCHAR(160) NOT NULL,
  convictedon DATE         NULL,     -- NULL until convicted; only a conviction counts
  atfault     TINYINT(1)   NULL,
  onnemt      TINYINT(1)   NOT NULL DEFAULT 1,   -- in the course of NEMT transportation
  note        VARCHAR(512) NULL,
  enteredby   VARCHAR(36)  NULL,
  createdon   DATETIME     NOT NULL,
  withdrawn   DATETIME     NULL,
  KEY ix_drivermovingviolations (accountid, driverid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO qualificationcatalog (code, name, area, sortorder) VALUES
  ('DRV-013', 'At-fault moving violations and accidents', 'licensing', 22),
  ('BKG-009', 'Social Security Death Master File check', 'background', 36);

INSERT IGNORE INTO credentialtypes (recordid, accountid, code, name, subject, maxagedays, requirestesting,
                                    defaultvaliddays, hasamount, category, description, added, active)
VALUES
  (UUID(), NULL, 'DMF_CHECK', 'Social Security Death Master File check', 'driver', NULL, 0, NULL, 0, 'screening', NULL, UTC_TIMESTAMP(), 1),
  (UUID(), NULL, 'GA_DRUG_LAW_PROCESS', 'Process for addressing state drug law violations', 'company', NULL, 0, NULL, 0, 'policy', NULL, UTC_TIMESTAMP(), 1),
  (UUID(), NULL, 'GA_DRIVER_HISTORY_PROCESS', 'Process for disclosing driver driving history', 'company', NULL, 0, NULL, 0, 'policy', NULL, UTC_TIMESTAMP(), 1),
  (UUID(), NULL, 'OWNER_EXCLUSION_CHECK', 'Owner and managing employee exclusion screening', 'company', NULL, 0, NULL, 0, 'screening', NULL, UTC_TIMESTAMP(), 1);

INSERT INTO compliancerules (recordid, accountid, code, qualificationcode, name, description, templatedocumentid, subject, authoritytype, authoritycategory, authority, jurisdiction, citation, sourceurl, applieswhen, program, evidencekind, evidencesource, origin, extendable, extendnote, offered, alternatesource, alternatewhen, reviewrequired, determination, blocking, gate, enforcement, legalreview, grouping, duestage, duedays, duetext, recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule, effectivefrom, effectiveto, supersedes, note, sortorder, added, addedby)
SELECT UUID(), NULL, 'GA_NET_ATFAULT', 'DRV-013', 'No more than one at-fault moving violation or accident (Georgia NEMT)', 'A driver convicted of two moving violations and/or accidents related to NEMT transportation where the driver was at fault must be removed from service. Counted from the accident register and the moving violations recorded on the driver.', templatedocumentid, subject, 'regulation', 'STATE_MEDICAID', 'Georgia DCH', 'GA', 'DCH NEMT Part II (October 2026), Section 914.2.5', NULL, '{"all":[{"any":[{"fact":"company.state","eq":"GA"},{"fact":"company.operatingstates","has":"GA"}]},{"fact":"company.medicaid","is":true}]}', 'medicaid', 'record', 'atfaultcount', 'office', extendable, extendnote, offered, NULL, NULL, reviewrequired, determination, 1, 'hardstop', enforcement, 'draft', 'regulatory', 'ongoing', duedays, duetext, 'ondocument', scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule, '2026-10-01', NULL, NULL, NULL, sortorder, UTC_TIMESTAMP(), NULL
FROM compliancerules WHERE code = 'DRIVER_LICENSE' AND accountid IS NULL AND effectiveto IS NULL
  AND NOT EXISTS (SELECT 1 FROM compliancerules x WHERE x.code = 'GA_NET_ATFAULT');

INSERT INTO compliancerules (recordid, accountid, code, qualificationcode, name, description, templatedocumentid, subject, authoritytype, authoritycategory, authority, jurisdiction, citation, sourceurl, applieswhen, program, evidencekind, evidencesource, origin, extendable, extendnote, offered, alternatesource, alternatewhen, reviewrequired, determination, blocking, gate, enforcement, legalreview, grouping, duestage, duedays, duetext, recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule, effectivefrom, effectiveto, supersedes, note, sortorder, added, addedby)
SELECT UUID(), NULL, 'GA_NET_DMF', 'BKG-009', 'Social Security Death Master File check', 'Each driver checked against the Social Security Administration''s Death Master File at hire and every year after. DCH places this duty on the broker; a broker may ask its transportation providers to carry it, and a company that does adopts this requirement.', templatedocumentid, subject, 'regulation', 'CONTRACT_COMPANY', 'Georgia DCH', 'GA', 'DCH NEMT Part II (October 2026), Section 608.7', NULL, '{"all":[{"any":[{"fact":"company.state","eq":"GA"},{"fact":"company.operatingstates","has":"GA"}]},{"fact":"company.medicaid","is":true}]}', 'medicaid', evidencekind, 'credential:DMF_CHECK', origin, 1, extendnote, 1, NULL, NULL, reviewrequired, determination, blocking, 'deficiency', enforcement, 'draft', 'company', 'prehire', duedays, duetext, 'days', scheduled, 365, violationresets, warndays, sensitivity, retentionrule, '2026-10-01', NULL, NULL, NULL, sortorder, UTC_TIMESTAMP(), NULL
FROM compliancerules WHERE code = 'FIRST_AID' AND accountid IS NULL AND effectiveto IS NULL
  AND NOT EXISTS (SELECT 1 FROM compliancerules x WHERE x.code = 'GA_NET_DMF');

INSERT INTO compliancerules (recordid, accountid, code, qualificationcode, name, description, templatedocumentid, subject, authoritytype, authoritycategory, authority, jurisdiction, citation, sourceurl, applieswhen, program, evidencekind, evidencesource, origin, extendable, extendnote, offered, alternatesource, alternatewhen, reviewrequired, determination, blocking, gate, enforcement, legalreview, grouping, duestage, duedays, duetext, recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule, effectivefrom, effectiveto, supersedes, note, sortorder, added, addedby)
SELECT UUID(), NULL, 'GA_NET_DRUG_LAW_PROCESS', NULL, 'Process for addressing state drug law violations (Georgia NEMT)', 'The transportation provider has a process in place to address any violation of a state drug law by its drivers. Filed as the written process.', templatedocumentid, subject, 'regulation', 'STATE_MEDICAID', 'Georgia DCH', 'GA', 'DCH NEMT Part II (October 2026), Section 915.1.3', NULL, '{"all":[{"any":[{"fact":"company.state","eq":"GA"},{"fact":"company.operatingstates","has":"GA"}]},{"fact":"company.medicaid","is":true}]}', 'medicaid', evidencekind, 'credential:GA_DRUG_LAW_PROCESS', origin, extendable, extendnote, offered, NULL, NULL, reviewrequired, determination, blocking, gate, enforcement, 'draft', grouping, duestage, duedays, duetext, recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule, '2026-10-01', NULL, NULL, NULL, sortorder, UTC_TIMESTAMP(), NULL
FROM compliancerules WHERE code = 'BBP_EXPOSURE_PLAN' AND accountid IS NULL AND effectiveto IS NULL
  AND NOT EXISTS (SELECT 1 FROM compliancerules x WHERE x.code = 'GA_NET_DRUG_LAW_PROCESS');

INSERT INTO compliancerules (recordid, accountid, code, qualificationcode, name, description, templatedocumentid, subject, authoritytype, authoritycategory, authority, jurisdiction, citation, sourceurl, applieswhen, program, evidencekind, evidencesource, origin, extendable, extendnote, offered, alternatesource, alternatewhen, reviewrequired, determination, blocking, gate, enforcement, legalreview, grouping, duestage, duedays, duetext, recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule, effectivefrom, effectiveto, supersedes, note, sortorder, added, addedby)
SELECT UUID(), NULL, 'GA_NET_DRIVER_HISTORY_PROCESS', NULL, 'Process for disclosing drivers'' driving history to Medicaid (Georgia NEMT)', 'The transportation provider has a process in place to disclose to the state Medicaid program the driving history, including any traffic violations, of each driver it employs. Filed as the written process.', templatedocumentid, subject, 'regulation', 'STATE_MEDICAID', 'Georgia DCH', 'GA', 'DCH NEMT Part II (October 2026), Section 915.1.4', NULL, '{"all":[{"any":[{"fact":"company.state","eq":"GA"},{"fact":"company.operatingstates","has":"GA"}]},{"fact":"company.medicaid","is":true}]}', 'medicaid', evidencekind, 'credential:GA_DRIVER_HISTORY_PROCESS', origin, extendable, extendnote, offered, NULL, NULL, reviewrequired, determination, blocking, gate, enforcement, 'draft', grouping, duestage, duedays, duetext, recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule, '2026-10-01', NULL, NULL, NULL, sortorder, UTC_TIMESTAMP(), NULL
FROM compliancerules WHERE code = 'BBP_EXPOSURE_PLAN' AND accountid IS NULL AND effectiveto IS NULL
  AND NOT EXISTS (SELECT 1 FROM compliancerules x WHERE x.code = 'GA_NET_DRIVER_HISTORY_PROCESS');

INSERT INTO compliancerules (recordid, accountid, code, qualificationcode, name, description, templatedocumentid, subject, authoritytype, authoritycategory, authority, jurisdiction, citation, sourceurl, applieswhen, program, evidencekind, evidencesource, origin, extendable, extendnote, offered, alternatesource, alternatewhen, reviewrequired, determination, blocking, gate, enforcement, legalreview, grouping, duestage, duedays, duetext, recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule, effectivefrom, effectiveto, supersedes, note, sortorder, added, addedby)
SELECT UUID(), NULL, 'GA_NET_OWNER_EXCLUSION', NULL, 'Owners and managing employees screened against the OIG and SAM.gov lists', 'The broker may not contract with a provider, owner or partnership on the OIG exclusion list or SAM.gov, and checks monthly. Filed each month as the record of the owners'' and managing employees'' screening.', templatedocumentid, subject, 'regulation', 'STATE_MEDICAID', 'Georgia DCH', 'GA', 'DCH NEMT Part II (October 2026), Sections 608.6 and 608.8', NULL, '{"all":[{"any":[{"fact":"company.state","eq":"GA"},{"fact":"company.operatingstates","has":"GA"}]},{"fact":"company.medicaid","is":true}]}', 'medicaid', evidencekind, 'credential:OWNER_EXCLUSION_CHECK', origin, extendable, extendnote, offered, NULL, NULL, reviewrequired, determination, blocking, gate, enforcement, 'draft', grouping, duestage, duedays, duetext, 'days', scheduled, 31, violationresets, warndays, sensitivity, retentionrule, '2026-10-01', NULL, NULL, NULL, sortorder, UTC_TIMESTAMP(), NULL
FROM compliancerules WHERE code = 'BBP_EXPOSURE_PLAN' AND accountid IS NULL AND effectiveto IS NULL
  AND NOT EXISTS (SELECT 1 FROM compliancerules x WHERE x.code = 'GA_NET_OWNER_EXCLUSION');
