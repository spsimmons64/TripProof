-- ################################################################################################
-- # 219 - the fleet gets a compliance file, which it has never had.
-- #
-- # `compliancerules.subject` has carried 'company' and 'driver' and nothing else, while seven
-- # vehicle credential types sat in the catalog with no rule pointing at any of them. So a vehicle
-- # could be unregistered, uninsured, never inspected and carrying a lift nobody had load tested,
-- # and TripProof had nothing to say. A driver qualification file is half of what an auditor asks
-- # for; the other half is the vehicle.
-- #
-- # The engine needed no new ideas for this - the stages, gates and expiry arithmetic never cared
-- # what the subject was - so what arrives here is the rules, and two records the fleet keeps that
-- # are not documents:
-- #
-- #   DRIVER VEHICLE INSPECTION REPORTS - 49 CFR 396.11. The 2014 rule removed the no-defect report
-- #   for most carriers AND KEPT IT for passenger-carrying vehicles, which is every vehicle in this
-- #   business. The compliance question that actually stops a vehicle is 396.11(c): a defect
-- #   reported and not corrected means it must not be dispatched. So the requirement is a hard stop
-- #   on an OPEN defect, and the reports themselves are the log behind it. No invented interval:
-- #   the row says when the last report was, and an office can see staleness without TripProof
-- #   turning a vehicle red on a date nobody set.
-- #
-- #   MAINTENANCE RECORDS - 49 CFR 396.3(b). Systematic inspection, repair and maintenance, with
-- #   records kept. A log of what was done, when, at what mileage and by whom.
-- #
-- # The county or municipal vehicle permit is deliberately NOT given a rule. Whether one is needed
-- # is a question about a particular county, and a rule that went red for every operator in America
-- # because some of them need a permit would be worse than no rule.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS vehicledvirs (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    vehicleid    VARCHAR(36)  NOT NULL,
    driverid     VARCHAR(36)  NULL,          -- who inspected it
    reportedon   DATE         NOT NULL,
    kind         VARCHAR(8)   NOT NULL,      -- pretrip | posttrip
    defects      TINYINT(1)   NOT NULL DEFAULT 0,
    defectnote   VARCHAR(512) NULL,
    -- 396.11(c): a defect that would affect safe operation must be corrected before dispatch, and
    -- the correction certified. Both halves are kept because the second is the one that lifts it.
    correctedon  DATE         NULL,
    correctedby  VARCHAR(160) NULL,
    certifiedon  DATE         NULL,
    documentid   VARCHAR(36)  NULL,
    note         VARCHAR(512) NULL,
    addedby      VARCHAR(36)  NULL,
    added        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted      DATETIME     NULL,
    PRIMARY KEY (recordid),
    KEY ix_vehicledvirs_vehicle (accountid, vehicleid, reportedon),
    KEY ix_vehicledvirs_open (accountid, vehicleid, defects, correctedon),
    CONSTRAINT fk_vehicledvirs_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vehiclemaintenance (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    vehicleid    VARCHAR(36)  NOT NULL,
    performedon  DATE         NOT NULL,
    kind         VARCHAR(12)  NOT NULL,      -- scheduled | repair | inspection
    odometer     INT          NULL,
    summary      VARCHAR(255) NOT NULL,
    vendor       VARCHAR(160) NULL,
    documentid   VARCHAR(36)  NULL,
    note         VARCHAR(512) NULL,
    addedby      VARCHAR(36)  NULL,
    added        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted      DATETIME     NULL,
    PRIMARY KEY (recordid),
    KEY ix_vehiclemaintenance_vehicle (accountid, vehicleid, performedon),
    CONSTRAINT fk_vehiclemaintenance_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype, authority,
                             citation, applieswhen, evidencekind, evidencesource, origin,
                             extendable, reviewrequired, determination, blocking, gate, grouping,
                             duestage, duetext, recurrence, recurrencedays, warndays, note,
                             sortorder, effectivefrom)
SELECT UUID(), 'vehicle', t.code, t.name, t.description, t.authoritytype, t.authority, t.citation,
       t.applieswhen, t.evidencekind, t.evidencesource, 'office', 0, 0, 0, 1, t.gate, t.grouping,
       'ongoing', t.duetext, t.recurrence, t.recurrencedays, t.warndays, NULL, t.sortorder,
       CURRENT_DATE
  FROM (
    SELECT 'VEHICLE_REGISTRATION' AS code, 'Vehicle registration' AS name,
           'The State registration for this vehicle. No vehicle is lawfully operated without a '
           'current one, which is why it stops the unit rather than noting a deficiency.'
             AS description,
           'regulation' AS authoritytype, 'State law' AS authority,
           'State motor vehicle registration law' AS citation, NULL AS applieswhen,
           'document' AS evidencekind, 'credential:VEHICLE_REGISTRATION' AS evidencesource,
           'hardstop' AS gate, 'regulatory' AS grouping, NULL AS duetext,
           'ondocument' AS recurrence, NULL AS recurrencedays, 30 AS warndays, 5 AS sortorder
    UNION ALL SELECT 'VEHICLE_INSURANCE_CARD', 'Proof of insurance carried in the vehicle',
           'The card or certificate kept in the vehicle itself. The company''s commercial auto '
           'policy is a separate requirement on the company; this is the proof that travels with '
           'the unit.',
           'regulation', 'State law', 'State financial responsibility law', NULL,
           'document', 'credential:VEHICLE_INSURANCE', 'deficiency', 'regulatory', NULL,
           'ondocument', NULL, 30, 6
    UNION ALL SELECT 'DOT_ANNUAL_INSPECTION', 'Annual DOT inspection',
           'Every commercial motor vehicle must pass a periodic inspection at least once every '
           'twelve months, and the report or decal must be retained. 49 CFR 396.17. A vehicle '
           'whose inspection has lapsed may not be operated.',
           'regulation', 'FMCSA', '49 CFR 396.17; 49 CFR 396.21',
           '{"fact":"vehicle.cmv_federal","is":true}',
           'document', 'credential:DOT_ANNUAL_INSPECTION', 'hardstop', 'regulatory',
           'Every twelve months', 'days', 365, 30, 10
    UNION ALL SELECT 'TRANSIT_VEHICLE_INSPECTION', 'Annual transit vehicle safety inspection',
           'Florida requires a covered bus transit operator to inspect every operable vehicle at '
           'least annually, by a qualified inspector, against the standards in its System Safety '
           'Program Plan.',
           'regulation', 'FDOT', 'F.A.C. 14-90.009', '{"fact":"company.transit","is":true}',
           'document', 'credential:VEHICLE_INSPECTION', 'deficiency', 'regulatory',
           'Every twelve months', 'days', 365, 30, 11
    UNION ALL SELECT 'DVIR', 'Driver vehicle inspection reports',
           'A driver operating a passenger-carrying commercial motor vehicle must report on its '
           'condition at the end of each driving day, whether or not anything is wrong - the 2014 '
           'rule dropped the no-defect report for freight and kept it for passenger vehicles. What '
           'stops a unit is 49 CFR 396.11(c): a defect that would affect safe operation must be '
           'corrected, and the correction certified, before the vehicle goes out again.',
           'regulation', 'FMCSA', '49 CFR 396.11; 49 CFR 396.13',
           '{"fact":"vehicle.cmv_federal","is":true}',
           'process', 'dvir', 'hardstop', 'regulatory',
           'A report at the end of each driving day', 'once', NULL, 30, 12
    UNION ALL SELECT 'MAINTENANCE_RECORDS', 'Systematic inspection, repair and maintenance',
           'A motor carrier must systematically inspect, repair and maintain every vehicle under '
           'its control, and keep the records. 49 CFR 396.3. What is kept here is the log: what '
           'was done, when, at what mileage and by whom.',
           'regulation', 'FMCSA', '49 CFR 396.3(a), (b)',
           '{"fact":"vehicle.cmv_federal","is":true}',
           'process', 'maintenance', 'deficiency', 'regulatory', NULL, 'days', 365, 60, 13
    UNION ALL SELECT 'LIFT_CERTIFICATION', 'Wheelchair lift certification',
           'The manufacturer''s certification for the lift or ramp fitted to this vehicle. 49 CFR '
           '38.23 sets what the equipment must do; this is the evidence that this unit''s '
           'equipment does it.',
           'regulation', 'US DOT', '49 CFR 38.23; 49 CFR 37.161',
           '{"fact":"vehicle.lift","is":true}',
           'document', 'credential:LIFT_CERTIFICATION', 'deficiency', 'regulatory', NULL,
           'ondocument', NULL, 30, 20
    UNION ALL SELECT 'LIFT_LOAD_TEST', 'Wheelchair lift load test',
           'A load test of the lift fitted to this vehicle. 49 CFR 37.163 requires accessibility '
           'features to be maintained in operative condition and repaired promptly; a load test is '
           'how an operator demonstrates the lift still carries what it is rated for.',
           'regulation', 'US DOT', '49 CFR 37.163', '{"fact":"vehicle.lift","is":true}',
           'document', 'credential:LIFT_LOAD_TEST', 'deficiency', 'regulatory', NULL,
           'ondocument', NULL, 30, 21
  ) AS t
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules c
                    WHERE c.subject = 'vehicle' AND c.code = t.code AND c.effectiveto IS NULL);
