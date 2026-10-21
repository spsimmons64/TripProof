-- ################################################################################################
-- # 331 - transit safety programs reach vehicles, one determination per vehicle per program.
-- #
-- # The Vehicle Determinations panel had a fixed "Chapter 14-90" column - Florida's, asked of every
-- # company in every state, and read by no rule. A program that governs vehicles now says so in the
-- # catalog; each vehicle of a company the program touches carries its own determination; and the
-- # program's vehicle rules read that determination. Unknown is never exempt: a vehicle nobody has
-- # determined leaves those rules under review.
-- #
-- # Florida 14-90 (F.A.C.) asks four things of every bus a covered system operates - "bus" there
-- # includes Type II vehicles: minibuses, vans, modified vans, station wagons and sedans
-- # (14-90.002(1)(b)):
-- #   * an annual safety inspection by a qualified inspector, with a written report (14-90.009);
-- #   * a preventive maintenance plan with tracked inspection and lubrication intervals, records
-- #     kept four years (14-90.004(4));
-- #   * a daily pre-operational inspection by the driver, defects reported and corrected, records
-- #     kept two weeks (14-90.006(8));
-- #   * the equipment standards of 14-90.007 - checked item by item in the annual inspection
-- #     (14-90.009(3)), so they are not a requirement of their own here.
-- # The first already existed and read a company-wide question; it now reads the vehicle. The other
-- # two are new, and go in as drafts until reviewed.
-- #
-- # The federal safety plan (49 CFR Part 673) governs the agency, not each vehicle, so it gets no
-- # vehicle determination.
-- ################################################################################################

ALTER TABLE transitsafetyprograms
  ADD COLUMN IF NOT EXISTS vehicles TINYINT(1) NOT NULL DEFAULT 0 AFTER sortorder;
UPDATE transitsafetyprograms SET vehicles = 1 WHERE code = 'FL_1490';

CREATE TABLE IF NOT EXISTS vehicletransitprograms (
  accountid     VARCHAR(36) NOT NULL,
  vehicleid     VARCHAR(36) NOT NULL,
  programcode   VARCHAR(24) NOT NULL,
  determination VARCHAR(12) NOT NULL,          -- covered | notcovered | review
  determinedon  DATETIME    NOT NULL,
  determinedby  VARCHAR(36) NULL,
  PRIMARY KEY (vehicleid, programcode),
  KEY ix_vehicletransitprograms (accountid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Every Chapter 14-90 answer already given for a vehicle carries over.
INSERT IGNORE INTO vehicletransitprograms (accountid, vehicleid, programcode, determination,
                                           determinedon, determinedby)
SELECT accountid, vehicleid, 'FL_1490', fdot1490, COALESCE(assessedon, UTC_TIMESTAMP()), assessedby
FROM vehicleassessments WHERE fdot1490 IN ('covered', 'notcovered', 'review');

-- The annual inspection reads the vehicle's own determination.
UPDATE compliancerules
   SET applieswhen = '{"fact":"vehicle.transit.FL_1490","is":true}',
       description = 'Florida requires a covered bus transit system to have every bus it operates - Type II vans, minibuses and sedans included - inspected at least annually by a qualified inspector, against the equipment list in 14-90.009(3), with a written report kept four years.'
 WHERE code = 'TRANSIT_VEHICLE_INSPECTION' AND accountid IS NULL AND effectiveto IS NULL;

-- Preventive maintenance, from the vehicle's maintenance log - the same evidence the federal rule reads.
INSERT INTO compliancerules (recordid, accountid, code, qualificationcode, name, description,
  templatedocumentid, subject, authoritytype, authoritycategory, authority, jurisdiction, citation,
  sourceurl, applieswhen, program, evidencekind, evidencesource, origin, extendable, extendnote,
  offered, alternatesource, alternatewhen, reviewrequired, determination, blocking, gate,
  enforcement, legalreview, legalreviewedby, legalreviewedon, grouping, duestage, duedays, duetext,
  recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule,
  effectivefrom, effectiveto, supersedes, note, sortorder, added, addedby)
SELECT UUID(), NULL, 'FL_TRANSIT_MAINTENANCE', NULL,
  'Preventive maintenance (Florida bus transit)',
  'Florida requires a covered bus transit system to inspect, maintain and lubricate every bus at intervals meeting or exceeding the manufacturer''s, track when each is due, and keep the records - date, mileage and what was done - for four years.',
  NULL, 'vehicle', 'regulation', NULL, 'FDOT', 'FL', 'F.A.C. 14-90.004(4)',
  'https://www.flrules.org/gateway/ruleNo.asp?id=14-90.004',
  '{"fact":"vehicle.transit.FL_1490","is":true}', NULL, r.evidencekind, r.evidencesource, r.origin,
  0, NULL, 0, NULL, NULL, 0, 0, 1, r.gate, r.enforcement, 'draft', NULL, NULL, 'regulatory',
  'ongoing', NULL, 'Every twelve months at the least', r.recurrence, 0, r.recurrencedays, 0,
  r.warndays, 'normal', NULL, CURDATE(), NULL, NULL,
  'Records kept four years (14-90.004(4)(d)).', r.sortorder + 1, UTC_TIMESTAMP(), NULL
FROM compliancerules r
WHERE r.code = 'MAINTENANCE_RECORDS' AND r.accountid IS NULL AND r.effectiveto IS NULL
  AND NOT EXISTS (SELECT 1 FROM compliancerules x WHERE x.code = 'FL_TRANSIT_MAINTENANCE');

-- The driver's daily inspection, from the vehicle's inspection reports - an open defect stops it.
INSERT INTO compliancerules (recordid, accountid, code, qualificationcode, name, description,
  templatedocumentid, subject, authoritytype, authoritycategory, authority, jurisdiction, citation,
  sourceurl, applieswhen, program, evidencekind, evidencesource, origin, extendable, extendnote,
  offered, alternatesource, alternatewhen, reviewrequired, determination, blocking, gate,
  enforcement, legalreview, legalreviewedby, legalreviewedon, grouping, duestage, duedays, duetext,
  recurrence, scheduled, recurrencedays, violationresets, warndays, sensitivity, retentionrule,
  effectivefrom, effectiveto, supersedes, note, sortorder, added, addedby)
SELECT UUID(), NULL, 'FL_TRANSIT_DAILY_INSPECTION', NULL,
  'Daily vehicle inspection (Florida bus transit)',
  'Florida requires a covered bus transit system to have each bus inspected before it operates each day - brakes, tires and wheels, steering, horn, lights, wipers, mirrors, passenger doors, exhaust, wheelchair equipment and safety equipment - with defects reported, reviewed and corrected.',
  NULL, 'vehicle', 'regulation', NULL, 'FDOT', 'FL', 'F.A.C. 14-90.006(8)',
  'https://www.flrules.org/gateway/ruleNo.asp?id=14-90.006',
  '{"fact":"vehicle.transit.FL_1490","is":true}', NULL, r.evidencekind, r.evidencesource, r.origin,
  0, NULL, 0, NULL, NULL, 0, 0, 1, r.gate, r.enforcement, 'draft', NULL, NULL, 'regulatory',
  'ongoing', NULL, 'Before the vehicle operates each day', r.recurrence, 0, r.recurrencedays, 0,
  r.warndays, 'normal', NULL, CURDATE(), NULL, NULL,
  'Reports and corrective actions kept at least two weeks (14-90.006(8)(c)).', r.sortorder + 1,
  UTC_TIMESTAMP(), NULL
FROM compliancerules r
WHERE r.code = 'DVIR' AND r.accountid IS NULL AND r.effectiveto IS NULL
  AND NOT EXISTS (SELECT 1 FROM compliancerules x WHERE x.code = 'FL_TRANSIT_DAILY_INSPECTION');
