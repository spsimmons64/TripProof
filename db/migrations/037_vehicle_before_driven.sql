-- ################################################################################################
-- # 037 - the vehicle catalog holds what must be in place before the vehicle is driven:
-- # certifications, inspections, registration, insurance and the maintenance records themselves.
-- #
-- # Out go the two day-to-day logs, which belong in reports rather than in a document list: the
-- # driver vehicle inspection report filled in at the end of each shift, and the voluntary daily
-- # pre-trip log kept on vans. The maintenance file stays - it is a standing record, and both the
-- # law and broker credentialing expect it to exist before a vehicle goes into service.
-- #
-- # The two maintenance rows are named apart so neither reads as a repeat of the other: the part 396
-- # file for commercial vehicles, and the preventive maintenance history brokers ask of vans.
-- ################################################################################################
DELETE FROM compliancedocs WHERE subject = 'vehicle' AND code IN ('DVIR', 'DAILY_INSPECTION_LOG');

UPDATE compliancedocs SET
    name = 'Wheelchair lift service and repair records',
    description = 'The ADA requires a lift, ramp or securement system to be kept in operative condition and repaired promptly, so the service history is what proves it.'
    WHERE subject = 'vehicle' AND code = 'LIFT_OPERATIVE';

UPDATE compliancedocs SET
    name = 'Vehicle maintenance and repair file (part 396)',
    description = 'Vehicle identification, the schedule of inspections due, the repair history, and tests of pushout windows and emergency doors on buses.'
    WHERE subject = 'vehicle' AND code = 'MAINTENANCE_FILE';

UPDATE compliancedocs SET
    name = 'Preventive maintenance schedule and service history',
    appliesif = 'Vehicle is below the commercial line',
    description = 'The manufacturer''s service schedule and what has been done against it. Not federal law for a van, but broker credentialing and insurers expect it.',
    sortorder = 300
    WHERE subject = 'vehicle' AND code = 'VEHICLE_MAINTENANCE';

INSERT IGNORE INTO compliancedocs
    (recordid, jurisdiction, subject, code, name, obligation, category, expires, driversign, renewal, appliesif,
     description, legalcitation, authority, sourceurl, sortorder)
VALUES
('c0666666-0000-4000-8000-000000000014', 'US', 'vehicle', 'TITLE_OR_LEASE', 'Proof of ownership or lease', 'recommended', 'operations', 0, 0,
 'At purchase or lease, and when the lease renews', '',
 'Title, bill of sale or the lease agreement. Broker credentialing asks for it before a vehicle is put into service.',
 NULL, 'Broker contracts', NULL, 305);

UPDATE compliancedocs SET sortorder = 315 WHERE subject = 'vehicle' AND code = 'VEHICLE_INSURANCE_CARD';
UPDATE compliancedocs SET sortorder = 325 WHERE subject = 'vehicle' AND code = 'LIFT_LOAD_TEST';
