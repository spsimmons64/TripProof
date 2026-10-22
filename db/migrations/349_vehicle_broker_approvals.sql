-- ################################################################################################
-- # 349 - which broker lines a vehicle is approved for, and from when (2026-10-22).
-- #
-- # A company with a Georgia Medicaid line does not run every van for the Georgia broker. The
-- # broker approves vehicles one by one, and DCH 910.2 counts the initial inspection back from the
-- # day each enters service: no earlier than sixty days before it. Kept like a driver's approvals -
-- # ended, never deleted.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS vehicleauthorizations (
    recordid     VARCHAR(36) NOT NULL,
    accountid    VARCHAR(36) NOT NULL,
    vehicleid    VARCHAR(36) NOT NULL,
    contractid   VARCHAR(36) NOT NULL,
    servicefrom  DATE        NOT NULL,
    approvedon   DATETIME    NOT NULL,
    approvedby   VARCHAR(36) NULL,
    endedon      DATETIME    NULL,
    endedby      VARCHAR(36) NULL,
    PRIMARY KEY (recordid),
    KEY ix_vehicleauthorizations (accountid, vehicleid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The Georgia broker inspection reaches a vehicle the Georgia Medicaid broker has approved - not
-- every vehicle of a company that has a Georgia line.
UPDATE compliancerules SET applieswhen = '{"all":[{"fact":"company.medicaidstates","has":"GA"},{"fact":"vehicle.medicaidstates","has":"GA"}]}',
       description = 'The Georgia Medicaid broker inspects each vehicle it approves before it enters service - no earlier than sixty days before - and again no later than six months after the last inspection (DCH 910.1, 910.2). Reaches a vehicle approved for a Georgia Medicaid line, from the date it entered that service.'
 WHERE code = 'GA_NET_VEHICLE_INSPECTION' AND accountid IS NULL AND effectiveto IS NULL;

-- A certified defect may have been repaired, or found to need no repair (49 CFR 396.11(a)(3)(ii)).
ALTER TABLE vehicledvirs ADD COLUMN IF NOT EXISTS correction VARCHAR(12) NULL AFTER correctedby;
UPDATE vehicledvirs SET correction = 'repaired' WHERE correctedon IS NOT NULL AND correction IS NULL;
UPDATE compliancerules
   SET description = REPLACE(description, 'must be repaired, and the repair certified,',
                             'must be repaired - or certified as needing no repair - and that certified')
 WHERE code = 'DVIR' AND accountid IS NULL AND effectiveto IS NULL;
