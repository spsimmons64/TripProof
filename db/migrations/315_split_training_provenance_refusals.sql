-- ################################################################################################
-- # 315 - passenger assistance apart from securement, where evidence came from, refused trips kept.
-- #
-- # Passenger assistance and wheelchair securement are two competencies. They were one requirement
-- # because one certificate covered both, and it still may: the combined certificate is accepted
-- # for passenger assistance where no separate record exists. A record of passenger assistance
-- # training on its own now answers that requirement without pretending to answer securement.
-- #
-- # Provenance: a Florida Level 1 is a screening run through the FDLE, or read from the AHCA
-- # Clearinghouse. A report that does not say which is a document, not a screening anybody can rely
-- # on, so it is on file and under review until somebody records where it came from.
-- #
-- # Refused assignments: an assignment refused by the trip check rolls back, and the check that
-- # refused it used to roll back with it. It is kept now, marked refused.
-- ################################################################################################

-- Securement is the securement certificate's own qualification now.
UPDATE qualificationcatalog SET name = 'Wheelchair securement training' WHERE code = 'TRN-003';
INSERT IGNORE INTO qualificationcatalog (code, name, area, sortorder) VALUES
  ('TRN-001', 'Passenger assistance and disability awareness training', 'training', 49);

INSERT IGNORE INTO credentialtypes (recordid, accountid, code, name, subject, maxagedays,
                                    requirestesting, defaultvaliddays, hasamount, category,
                                    description, added, active)
VALUES (UUID(), NULL, 'PASSENGER_ASSISTANCE', 'Passenger assistance and disability awareness training',
        'driver', NULL, 0, NULL, 0, 'training',
        'A certificate of completion, or the company''s own record of the training given. Record who provided it.',
        UTC_TIMESTAMP(), 1);

-- The new rule copies everything about the securement rule but what it proves and what answers
-- it: same reach, same stage, same gate. Where the driver has no separate record, the combined
-- securement certificate is accepted - that is what alternatesource does, and alternatewhen left
-- empty means always.
INSERT INTO compliancerules (recordid, accountid, code, qualificationcode, name, description,
    templatedocumentid, subject, authoritytype, authoritycategory, authority, jurisdiction, citation,
    sourceurl, applieswhen, program, evidencekind, evidencesource, origin, extendable, extendnote,
    offered, alternatesource, alternatewhen, reviewrequired, determination, blocking, gate,
    enforcement, legalreview, grouping, duestage, duedays, duetext, recurrence, scheduled,
    recurrencedays, violationresets, warndays, sensitivity, retentionrule, effectivefrom,
    effectiveto, supersedes, note, sortorder, added, addedby)
SELECT UUID(), NULL, 'PASSENGER_ASSISTANCE_TRAINING', 'TRN-001',
    'Passenger assistance and disability awareness training',
    'Training in assisting passengers with disabilities and treating them with courtesy, to proficiency for the duties performed. The combined passenger assistance and securement certificate is accepted where there is no separate record.',
    templatedocumentid, subject, authoritytype, authoritycategory, authority, jurisdiction,
    '49 CFR 37.173', sourceurl, applieswhen, program, evidencekind,
    'credential:PASSENGER_ASSISTANCE', origin, extendable, extendnote, offered,
    'credential:WHEELCHAIR_SECUREMENT', NULL, reviewrequired, determination, blocking, gate,
    enforcement, 'draft', grouping, duestage, duedays, duetext, recurrence, scheduled,
    recurrencedays, violationresets, warndays, sensitivity, retentionrule, effectivefrom, NULL, NULL,
    NULL, sortorder - 1, UTC_TIMESTAMP(), NULL
FROM compliancerules
WHERE code = 'SECUREMENT_TRAINING_CERT' AND subject = 'driver' AND accountid IS NULL
  AND effectiveto IS NULL
  AND NOT EXISTS (SELECT 1 FROM compliancerules x WHERE x.code = 'PASSENGER_ASSISTANCE_TRAINING');

-- Where a screening came from, on the record, and which kinds of record have to say.
ALTER TABLE credentials ADD COLUMN IF NOT EXISTS provenance VARCHAR(24) NULL AFTER issuer;
  -- fdle | ahca | vendor
ALTER TABLE credentialtypes ADD COLUMN IF NOT EXISTS requiresprovenance TINYINT(1) NOT NULL DEFAULT 0;
UPDATE credentialtypes SET requiresprovenance = 1 WHERE code = 'FL_LEVEL1' AND accountid IS NULL;

ALTER TABLE tripeligibility ADD COLUMN IF NOT EXISTS refused TINYINT(1) NOT NULL DEFAULT 0 AFTER shadow;
