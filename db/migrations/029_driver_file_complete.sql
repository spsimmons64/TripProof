-- ################################################################################################
-- # 029 - the rest of the driver file: hiring paperwork, screening results and training records.
-- #
-- # 028 covered the FMCSA side, which mostly reaches CDL and commercial-vehicle drivers. What was
-- # missing is everything a typical NEMT driver file holds anyway: the application and tax forms,
-- # per-driver exclusion screening, drug testing below the CDL line, registry checks, fingerprints,
-- # and the training certificates (PASS, securement, CPR, first aid, HIPAA, bloodborne pathogens).
-- #
-- # The employment application also stops being CDL-only: every company takes one. Part 391 only
-- # dictates its contents for commercial drivers, which the note now says.
-- #
-- # Citations checked against eCFR text on 2026-09-22. Where no federal rule reaches an item for a
-- # typical NEMT van driver, authority names who does demand it (broker contracts, State law) and
-- # the row is recommended rather than invented as law.
-- ################################################################################################
SET @ecfr = 'https://www.ecfr.gov/current/title-';

UPDATE compliancedocs SET obligation = 'required', appliesif = '',
    description = 'The application and hiring paperwork the company keeps on file. For commercial drivers part 391 fixes what it must contain: addresses, employers and accidents for the prior 3 years.'
    WHERE jurisdiction = 'US' AND code = 'EMPLOYMENT_APPLICATION';

INSERT IGNORE INTO compliancedocs
    (recordid, jurisdiction, subject, code, name, obligation, category, expires, driversign, renewal, appliesif,
     description, legalcitation, authority, sourceurl, sortorder)
VALUES
-- Required ---------------------------------------------------------------------------------------
('c0444444-0000-4000-8000-000000000001', 'US', 'driver', 'W4', 'Form W-4 withholding certificate', 'required', 'employment', 0, 1,
 'On or before the first day of employment, and again when the driver changes it', '',
 'Signed by the employee and kept with the payroll records.',
 '26 CFR 31.3402(f)(2)-1', 'IRS', CONCAT(@ecfr, '26/section-31.3402(f)(2)-1'), 125),
('c0444444-0000-4000-8000-000000000002', 'US', 'driver', 'EXCLUSION_CHECK_DRIVER', 'Exclusion screening result (OIG LEIE and SAM.gov)', 'required', 'screening', 1, 0,
 'Monthly', '', 'The per-driver result behind the company''s screening programme. No federal health care program money may pay for anything furnished by an excluded person.',
 '42 U.S.C. 1396a(a)(87)(A); 42 CFR 1001.1901', 'Congress (CAA 2021 §209); HHS-OIG', 'https://oig.hhs.gov/exclusions/', 135),
('c0444444-0000-4000-8000-000000000003', 'US', 'driver', 'PASS_TRAINING', 'Passenger assistance training certificate (PASS or equivalent)', 'required', 'training', 1, 0,
 'Per the training provider; two years is common', '',
 'The ADA requires personnel to be trained to proficiency to assist and treat riders with disabilities; the certificate is the proof.',
 '49 CFR 37.173', 'U.S. DOT (ADA)', CONCAT(@ecfr, '49/section-37.173'), 145),
('c0444444-0000-4000-8000-000000000004', 'US', 'driver', 'HIPAA_TRAINING_DRIVER', 'HIPAA training certificate', 'required', 'privacy', 1, 0,
 'Periodic; annual is the common practice', 'Drivers see passenger names, addresses and destinations',
 'Each workforce member''s training record under the security awareness and training standard.',
 '45 CFR 164.308(a)(5)', 'HHS (HIPAA)', CONCAT(@ecfr, '45/section-164.308'), 155),
-- Required if ------------------------------------------------------------------------------------
('c0444444-0000-4000-8000-000000000005', 'US', 'driver', 'SECUREMENT_TRAINING_CERT', 'Wheelchair securement training certificate', 'conditional', 'training', 1, 0,
 'Per the training provider; two years is common', 'Carries passengers who use wheelchairs or other mobility aids',
 'Operating the lift and securement system safely is part of the ADA training duty.',
 '49 CFR 37.173', 'U.S. DOT (ADA)', CONCAT(@ecfr, '49/section-37.173'), 225),
('c0444444-0000-4000-8000-000000000006', 'US', 'driver', 'BBP_TRAINING', 'Bloodborne pathogens training record', 'conditional', 'safety', 1, 0,
 'At initial assignment and at least annually thereafter', 'Staff can reasonably be expected to contact blood or other potentially infectious material',
 'Training records are kept 3 years; the hepatitis B vaccination offer and any declination belong with them.',
 '29 CFR 1910.1030(g)(2)', 'OSHA', CONCAT(@ecfr, '29/section-1910.1030'), 235),
('c0444444-0000-4000-8000-000000000007', 'US', 'driver', 'RANDOM_TESTING_RECORDS', 'Random drug and alcohol testing records', 'conditional', 'screening', 0, 0,
 'Throughout the year, at the rates FMCSA sets', 'CDL drivers subject to part 382 testing',
 'Selection records and results for each testing period.',
 '49 CFR 382.305', 'FMCSA', CONCAT(@ecfr, '49/section-382.305'), 245),
('c0444444-0000-4000-8000-000000000008', 'US', 'driver', 'FINGERPRINT_SCREENING', 'Fingerprint-based background screening', 'conditional', 'screening', 1, 0,
 'Per the State; five years is common', 'The State or the broker requires fingerprint-based screening (Florida Level 2, for example)',
 'A name-based check is not the same thing; several States require fingerprints against State and FBI records.',
 NULL, 'State law and broker contracts', NULL, 255),
-- Recommended ------------------------------------------------------------------------------------
('c0444444-0000-4000-8000-000000000009', 'US', 'driver', 'DRUG_SCREEN_NONCDL', 'Pre-employment drug screen (non-CDL driver)', 'recommended', 'screening', 0, 0,
 'At hire', 'Driver is not subject to part 382 testing',
 'Below the CDL line no federal rule requires it, but broker contracts and State programmes usually do.',
 NULL, 'Broker and State contracts', NULL, 270),
('c0444444-0000-4000-8000-000000000010', 'US', 'driver', 'SEX_OFFENDER_CHECK', 'Sex offender registry check', 'recommended', 'screening', 1, 0,
 'At hire, then on the broker''s or State''s recheck cycle', '',
 'Standard for anyone transporting vulnerable passengers; several States require it outright.',
 NULL, 'State law and broker contracts', 'https://www.nsopw.gov/', 275),
('c0444444-0000-4000-8000-000000000011', 'US', 'driver', 'ABUSE_REGISTRY_CHECK', 'Abuse or adult protective registry check', 'recommended', 'screening', 1, 0,
 'At hire, then on the broker''s or State''s recheck cycle', 'Carries elderly or disabled passengers',
 'Where a State runs an abuse registry, screening against it is usually part of the contract.',
 NULL, 'State law and broker contracts', NULL, 280),
('c0444444-0000-4000-8000-000000000012', 'US', 'driver', 'CPR_FIRST_AID', 'CPR and first aid certification', 'recommended', 'training', 1, 0,
 'Per the certifying body; two years is common', '',
 'Not federal law for NEMT, but broker contracts and stretcher or wheelchair work routinely require it.',
 NULL, 'Broker and State contracts', NULL, 285),
('c0444444-0000-4000-8000-000000000013', 'US', 'driver', 'DEFENSIVE_DRIVING', 'Defensive driving course certificate', 'recommended', 'training', 1, 0,
 'Per the course; three years is common', '', 'Often required by the insurer rather than by law.',
 NULL, 'Insurers and broker contracts', NULL, 290),
('c0444444-0000-4000-8000-000000000014', 'US', 'driver', 'EMERGENCY_CONTACT', 'Emergency contact and personal details form', 'recommended', 'employment', 0, 1,
 'On hire, updated as needed', '', 'Who to call, and any information dispatch needs in an incident.',
 NULL, 'Good practice', NULL, 295);
