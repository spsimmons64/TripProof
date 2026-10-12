-- ################################################################################################
-- # 066 - the driver's PHI confidentiality and privacy acknowledgment.
-- #
-- # A driver sees who is being carried, where they are going and why - names, addresses, appointment
-- # locations, mobility needs. The company's acknowledgment of what may be done with that is its own
-- # document, like the drug and alcohol policy and the workplace policy: the account files its copy,
-- # the applicant is shown that copy, and signs against it.
-- #
-- # Two things are needed for that: somewhere for the account to file it, and the driver-side item it
-- # answers. The item already exists (PHI_CONFIDENTIALITY); this is the company side.
-- ################################################################################################
INSERT IGNORE INTO credentialtypes (recordid, code, name, subject, maxagedays, defaultvaliddays, category, description, active)
VALUES (UUID(), 'PHI_POLICY', 'Driver PHI confidentiality and privacy acknowledgment', 'company', NULL, NULL,
        'privacy', 'The acknowledgment every driver signs about passenger information: what it covers, what '
        'they may do with it, and that the duty continues after the trip and after they leave', 1);

-- The company-side document this account files, and the driver-side item a signature answers.
UPDATE compliancedocs
   SET name        = 'PHI confidentiality and privacy acknowledgment',
       obligation  = 'conditional', classification = 'conditional',
       appliesif   = 'Drivers see passenger names, addresses, destinations or medical information',
       driversign  = 1,
       whendue     = 'Before the driver carries a passenger',
       description = 'Signed by the driver: what counts as confidential passenger information, that it is '
                     'used only for the job, that it is never discussed or posted, that incidents are '
                     'reported, and that the duty continues after the trip and after they leave.'
 WHERE subject = 'driver' AND code = 'PHI_CONFIDENTIALITY';

INSERT IGNORE INTO compliancedocs
    (recordid, jurisdiction, sourcecode, subject, code, name, obligation, classification, requiredfor,
     category, expires, driversign, renewal, whendue, appliesif, description, legalcitation, authority,
     sortorder, active)
VALUES (UUID(), 'US', 'FED_HIPAA', 'company', 'PHI_POLICY',
        'Driver PHI confidentiality and privacy acknowledgment', 'conditional', 'conditional', 'both',
        'privacy', 0, 1, 'Reissue when the policy changes', 'Before drivers carry passengers',
        'Drivers see passenger names, addresses, destinations or medical information',
        'The company''s own acknowledgment, shown to every applicant and signed by them.',
        '45 CFR 164.530(b)(1)', 'HHS', 415, 1);
