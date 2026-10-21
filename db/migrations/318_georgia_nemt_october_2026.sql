-- ################################################################################################
-- # 318 - Georgia NEMT rules brought to the October 2026 manual.
-- #
-- # DCH Part II Policies and Procedures for Non-Emergency Medical Transportation, version date
-- # October 1, 2026 (Seed Data/GA). The driver requirements are the 2016 ones, renumbered: 300.12 is
-- # now 914, 300.13 is 916, 400.6(5) is 1006.5. Two things are new and are added here:
-- #
-- #   915.1.1  each driver not excluded from federal health care programs (the OIG list) - a Georgia
-- #            source on the OIG exclusion screening;
-- #   915.1.2  each driver holds a valid license - added to the license rule's citation.
-- #
-- # 915.1.3 and 915.1.4 (a process for state drug-law violations, a process to disclose drivers'
-- # driving history) are the provider's procedures, not a driver's qualification, and are not here.
-- # Everything stays a draft until reviewed.
-- ################################################################################################

UPDATE compliancerules SET citation = 'DCH NEMT Part II (October 2026), Section 914.2.1', effectivefrom = '2026-10-01'
 WHERE code = 'GA_NET_AGE21' AND accountid IS NULL AND effectiveto IS NULL;
UPDATE compliancerules SET citation = 'DCH NEMT Part II (October 2026), Sections 914.1, 914.2.1 and 915.1.2', effectivefrom = '2026-10-01'
 WHERE code = 'GA_NET_LICENSE' AND accountid IS NULL AND effectiveto IS NULL;
UPDATE compliancerules SET citation = 'DCH NEMT Part II (October 2026), Section 1006.5.2', effectivefrom = '2026-10-01'
 WHERE code = 'GA_NET_LICENSE_COPY' AND accountid IS NULL AND effectiveto IS NULL;
UPDATE compliancerules SET citation = 'DCH NEMT Part II (October 2026), Sections 914.2.4 and 1006.5.3', effectivefrom = '2026-10-01'
 WHERE code = 'GA_NET_MVR' AND accountid IS NULL AND effectiveto IS NULL;
UPDATE compliancerules SET citation = 'DCH NEMT Part II (October 2026), Sections 914.2.2, 914.2.3 and 1006.5.4', effectivefrom = '2026-10-01'
 WHERE code = 'GA_NET_BACKGROUND' AND accountid IS NULL AND effectiveto IS NULL;
UPDATE compliancerules SET citation = 'DCH NEMT Part II (October 2026), Sections 916.1.3, 916.2 and 1006.5.6', effectivefrom = '2026-10-01'
 WHERE code = 'GA_NET_DRIVER_TRAINING' AND accountid IS NULL AND effectiveto IS NULL;
UPDATE compliancerules SET citation = 'DCH NEMT Part II (October 2026), Sections 916.1, 916.2 and 1006.5.5', effectivefrom = '2026-10-01'
 WHERE code = 'GA_NET_FIRST_AID' AND accountid IS NULL AND effectiveto IS NULL;
UPDATE compliancerules SET citation = 'DCH NEMT Part II (October 2026), Sections 916.1.1 and 916.2', effectivefrom = '2026-10-01'
 WHERE code = 'GA_NET_PASSENGER_ASSIST' AND accountid IS NULL AND effectiveto IS NULL;
UPDATE compliancerules SET citation = 'DCH NEMT Part II (October 2026), Sections 916.1.2 and 916.2', effectivefrom = '2026-10-01'
 WHERE code = 'GA_NET_SAFETY_SENSITIVITY' AND accountid IS NULL AND effectiveto IS NULL;
UPDATE compliancerules SET citation = 'DCH NEMT Part II (October 2026), Sections 916.1 and 916.2', effectivefrom = '2026-10-01'
 WHERE code = 'GA_NET_SPILL_KIT' AND accountid IS NULL AND effectiveto IS NULL;

INSERT INTO compliancerules (recordid, accountid, code, qualificationcode, name, description, templatedocumentid, subject, authoritytype, authoritycategory, authority, jurisdiction, citation, sourceurl, applieswhen, program, evidencekind, evidencesource, origin, extendable, extendnote, offered, alternatesource, alternatewhen, reviewrequired, determination, blocking, gate, enforcement, legalreview, grouping, duestage, duedays, duetext, recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule, effectivefrom, effectiveto, supersedes, note, sortorder, added, addedby)
SELECT UUID(), NULL, 'GA_NET_OIG', 'BKG-001', 'Not excluded from federal health care programs (Georgia NEMT)', description, templatedocumentid, subject, 'regulation', 'STATE_MEDICAID', 'Georgia DCH', 'GA', 'DCH NEMT Part II (October 2026), Section 915.1.1', NULL, '{"all":[{"any":[{"fact":"company.state","eq":"GA"},{"fact":"company.operatingstates","has":"GA"}]},{"fact":"company.medicaid","is":true}]}', 'medicaid', evidencekind, evidencesource, origin, extendable, extendnote, offered, alternatesource, alternatewhen, reviewrequired, determination, blocking, gate, enforcement, 'draft', grouping, duestage, duedays, duetext, recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule, '2026-10-01', NULL, NULL, NULL, sortorder, UTC_TIMESTAMP(), NULL
FROM compliancerules WHERE code = 'EXCLUSION_OIG_LEIE' AND subject = 'driver' AND accountid IS NULL
  AND effectiveto IS NULL
  AND NOT EXISTS (SELECT 1 FROM compliancerules x WHERE x.code = 'GA_NET_OIG');
