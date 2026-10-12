-- ################################################################################################
-- # 102 - the Florida Class E NEMT driver, corrected.
-- #
-- # Four things this catalog had wrong or missing for the ordinary case: a Florida driver carrying
-- # Medicaid passengers in a sedan, van or wheelchair vehicle on a Class E licence.
-- #
-- # 1. Florida Level 1 screening was missing entirely. F.S. 409.907 says Medicaid nonemergency
-- #    transportation drivers employed by or contracted with transportation companies, TNCs or
-- #    brokers are NOT subject to Level 2 screening, but must meet Level 1 under Chapter 435 or an
-- #    authorised equivalent. The catalog held only Level 2, so the requirement that actually
-- #    reaches these drivers was nowhere, and the one that does not was the only one on offer.
-- #
-- # 2. Level 2 said nothing about that carve-out, so an office reading it would assume it applied.
-- #
-- # 3. The driving-record item read as though the statute demanded an MVR. 42 U.S.C. 1396a(a)(87)(D)
-- #    requires the provider to have a process to disclose each driver's driving history, including
-- #    traffic violations, to the state. An MVR is how TripProof satisfies that - which is a sound
-- #    mechanism and not the same thing as the requirement.
-- #
-- # 4. The PHI acknowledgement was cited to 45 CFR 164.308(a)(1)(ii)(C). That provision is about a
-- #    covered entity's internal sanctions policy; it does not make every NEMT driver sign an
-- #    acknowledgement. It is good practice and often a contract term, and it is now described as
-- #    what it is.
-- ################################################################################################
INSERT IGNORE INTO compliancedocs
    (recordid, jurisdiction, sourcecode, triggercode, subject, code, name, obligation, classification,
     requiredfor, category, stage, expires, driversign, whendue, retention, appliesif, description,
     legalcitation, authority, sourceurl, sortorder, active, added)
VALUES (UUID(), 'FL', 'FL_AHCA', 'MEDICAID_TRIPS', 'driver', 'FL_LEVEL1_DRIVER',
        'Florida Level 1 background screening', 'conditional', 'conditional', 'both',
        'screening', 'prehire', 0, 0,
        'Before the driver carries a Medicaid passenger',
        'Kept for as long as the driver drives, and five years after',
        'Drivers carrying Florida Medicaid nonemergency transportation',
        'Statewide criminal records check under Chapter 435, or an authorised equivalent. Florida '
        'expressly does not subject Medicaid nonemergency transportation drivers to Level 2 '
        'screening - this is the screening that reaches them.',
        'F.S. 409.907; Ch. 435 F.S.', 'Florida AHCA',
        'https://www.flsenate.gov/Laws/Statutes/2023/409.907', 95, 1, UTC_TIMESTAMP());

UPDATE compliancedocs
   SET appliesif = 'Drivers in a programme that requires Level 2 - not ordinary Medicaid NEMT drivers',
       description = 'Level 2 screening under F.S. 435.04. Florida does not subject Medicaid '
                     'nonemergency transportation drivers employed by or contracted with '
                     'transportation companies, transportation network companies or brokers to '
                     'Level 2; those drivers are screened at Level 1. This applies where another '
                     'programme the company operates under calls for Level 2.'
 WHERE code = 'FL_LEVEL2_DRIVER' AND subject = 'driver';

UPDATE compliancedocs
   SET description = 'Federal Medicaid law requires the provider to have a process for disclosing '
                     'each driver''s driving history, including traffic violations, to the state. '
                     'TripProof satisfies that with a motor vehicle record obtained from the '
                     'licensing state and read by the office - the record is the mechanism, the '
                     'disclosure process is the requirement.'
 WHERE code = 'MVR_FILE' AND subject = 'driver';

UPDATE compliancedocs
   SET classification = 'contractual',
       legalcitation = 'Employer policy; HIPAA workforce training at 45 CFR 164.530(b)',
       appliesif = 'Companies that handle protected health information and ask drivers to acknowledge it',
       description = 'The driver''s written acknowledgement that they will keep passenger health '
                     'information confidential. HIPAA requires a covered entity to train its '
                     'workforce; it does not require this acknowledgement of every driver. It is '
                     'kept because employers and brokers commonly ask for it.'
 WHERE code = 'PHI_CONFIDENTIALITY' AND subject = 'driver';

-- The new item reaches the accounts that already exist, switched off until the company says it
-- carries Medicaid trips - which is the question that turns it on.
INSERT IGNORE INTO accountqualifications
    (recordid, accountid, subject, code, catalog, stage, applies, obligation, requiredfor, expires,
     validdays, sortorder)
SELECT UUID(), a.recordid, c.subject, c.code, 1, c.stage, 'off', c.obligation, c.requiredfor,
       c.expires, c.validdays, c.sortorder
  FROM accounts a CROSS JOIN compliancedocs c
 WHERE c.code = 'FL_LEVEL1_DRIVER' AND a.deleted IS NULL;
