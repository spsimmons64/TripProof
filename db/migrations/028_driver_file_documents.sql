-- ################################################################################################
-- # 028 - what belongs in a driver's file besides the policies they sign: the screening a company
-- # runs on a driver and the paper it keeps on them.
-- #
-- # Most of part 391 (driver qualification file, MVRs, road test, medical certificate) and part 382
-- # (drug testing, Clearinghouse) reach a driver only when the vehicle is a commercial motor
-- # vehicle or the driver holds a CDL, so those rows are conditional and name the condition. A
-- # typical NEMT van is below that line: there the broker contract and State law set the bar, which
-- # is why PSP, CDLIS and criminal background checks sit under "recommended" federally.
-- #
-- # Citations checked against the eCFR text on 2026-09-22. 49 CFR 391.27 is [Reserved] - the annual
-- # list of violations it once required is gone, folded into the 391.25 annual review.
-- # The annual Clearinghouse query moves from the company catalog to here: it is a per-driver record.
-- ################################################################################################
SET @ecfr = 'https://www.ecfr.gov/current/title-';

UPDATE compliancedocs SET subject = 'driver', sortorder = 250
    WHERE jurisdiction = 'US' AND code = 'CLEARINGHOUSE';

INSERT IGNORE INTO compliancedocs
    (recordid, jurisdiction, subject, code, name, obligation, category, expires, driversign, renewal, appliesif,
     description, legalcitation, authority, sourceurl, sortorder)
VALUES
-- Required of every NEMT driver ------------------------------------------------------------------
('c0333333-0000-4000-8000-000000000001', 'US', 'driver', 'DRIVER_LICENSE_COPY', 'Copy of the driver''s license', 'required', 'licensing', 1, 0,
 'Expiry printed on the license', '', 'Federal law requires every NEMT driver to hold a valid license; the file keeps the proof. A CDL driver''s license is also governed by 49 CFR part 383.',
 '42 U.S.C. 1396a(a)(87)(B)', 'Congress (CAA 2021 §209)', 'https://uscode.house.gov/view.xhtml?req=granuleid:USC-prefix-title42-section1396a&num=0&edition=prelim', 120),
('c0333333-0000-4000-8000-000000000002', 'US', 'driver', 'MVR_FILE', 'Motor vehicle record (driving history)', 'required', 'screening', 1, 0,
 'At hire, then on the company''s recheck cycle', '',
 'The driving history the company must be able to disclose to the State Medicaid program. For commercial drivers the timing is fixed: a 3-year record within 30 days of hire and a review every 12 months (49 CFR 391.23(a)(1), 391.25).',
 '42 U.S.C. 1396a(a)(87)(D)', 'Congress (CAA 2021 §209)', 'https://uscode.house.gov/view.xhtml?req=granuleid:USC-prefix-title42-section1396a&num=0&edition=prelim', 130),
-- Required if ------------------------------------------------------------------------------------
('c0333333-0000-4000-8000-000000000003', 'US', 'driver', 'DQ_FILE', 'Driver qualification file', 'conditional', 'employment', 0, 0,
 'Kept for the whole of employment and 3 years after', 'Drivers of commercial motor vehicles',
 'The file itself: employment application, MVR, road test certificate, medical certificate and the annual review.',
 '49 CFR 391.51', 'FMCSA', CONCAT(@ecfr, '49/section-391.51'), 140),
('c0333333-0000-4000-8000-000000000004', 'US', 'driver', 'EMPLOYMENT_APPLICATION', 'Employment application (3-year history)', 'conditional', 'employment', 0, 0,
 'On hire', 'Drivers of commercial motor vehicles', 'The application form part 391 prescribes, including addresses, employers and accidents for the prior 3 years.',
 '49 CFR 391.21', 'FMCSA', CONCAT(@ecfr, '49/section-391.21'), 150),
('c0333333-0000-4000-8000-000000000005', 'US', 'driver', 'MVR_PREEMPLOYMENT', 'Motor vehicle record at hire (3-year, each licensing authority)', 'conditional', 'screening', 0, 0,
 'Within 30 days of the date employment begins', 'Drivers of commercial motor vehicles',
 'One inquiry to every State where the driver held a license in the preceding 3 years.',
 '49 CFR 391.23(a)(1)', 'FMCSA', CONCAT(@ecfr, '49/section-391.23'), 160),
('c0333333-0000-4000-8000-000000000006', 'US', 'driver', 'MVR_ANNUAL', 'Annual motor vehicle record and review', 'conditional', 'screening', 1, 0,
 'At least once every 12 months', 'Drivers of commercial motor vehicles',
 'A fresh record plus the company''s written review of whether the driver still meets the standard. (49 CFR 391.27, the old annual list of violations, is now reserved.)',
 '49 CFR 391.25', 'FMCSA', CONCAT(@ecfr, '49/section-391.25'), 170),
('c0333333-0000-4000-8000-000000000007', 'US', 'driver', 'SAFETY_PERFORMANCE_HISTORY', 'Previous employer safety performance history', 'conditional', 'screening', 0, 0,
 'At hire; kept in a secure file with controlled access', 'Drivers of commercial motor vehicles',
 'Investigation of the driver''s accidents and drug and alcohol history with DOT-regulated employers over the prior 3 years.',
 '49 CFR 391.23(d), (e); 49 CFR 391.53', 'FMCSA', CONCAT(@ecfr, '49/section-391.53'), 180),
('c0333333-0000-4000-8000-000000000008', 'US', 'driver', 'MEDICAL_CERT', 'Medical examiner''s certificate', 'conditional', 'licensing', 1, 0,
 'At most every 24 months, sooner if the examiner shortens it', 'Drivers of commercial motor vehicles',
 'Examination by a medical examiner on the National Registry. Below the commercial threshold, a physical is usually a broker or State requirement instead.',
 '49 CFR 391.43; 49 CFR 391.45', 'FMCSA', CONCAT(@ecfr, '49/section-391.45'), 190),
('c0333333-0000-4000-8000-000000000009', 'US', 'driver', 'ROAD_TEST', 'Road test certificate or accepted equivalent', 'conditional', 'employment', 0, 0,
 'On hire', 'Drivers of commercial motor vehicles', 'The company''s road test, or the license or certificate accepted in its place.',
 '49 CFR 391.31; 49 CFR 391.33', 'FMCSA', CONCAT(@ecfr, '49/section-391.31'), 200),
('c0333333-0000-4000-8000-000000000010', 'US', 'driver', 'PREEMPLOYMENT_DRUG_TEST', 'Pre-employment controlled substances test', 'conditional', 'screening', 0, 0,
 'Before the driver first performs a safety-sensitive function', 'CDL drivers subject to part 382 testing',
 'A verified negative result before the driver may drive.',
 '49 CFR 382.301', 'FMCSA', CONCAT(@ecfr, '49/section-382.301'), 210),
('c0333333-0000-4000-8000-000000000011', 'US', 'driver', 'CLEARINGHOUSE_PREEMP', 'Clearinghouse pre-employment full query', 'conditional', 'screening', 0, 0,
 'Before the driver first performs a safety-sensitive function', 'CDL drivers subject to part 382 testing',
 'A full query, with the driver''s consent, before the driver may drive.',
 '49 CFR 382.701(a)', 'FMCSA', CONCAT(@ecfr, '49/section-382.701'), 220),
-- Recommended ------------------------------------------------------------------------------------
('c0333333-0000-4000-8000-000000000012', 'US', 'driver', 'PSP_REPORT', 'PSP report (FMCSA Pre-Employment Screening Program)', 'recommended', 'screening', 0, 0,
 'At hire', 'Hiring a driver with a commercial driving history',
 'Five years of crashes and three years of roadside inspections from MCMIS. Voluntary, and it needs the driver''s written consent under the FCRA.',
 '49 U.S.C. 31106(e)', 'FMCSA', 'https://psp.fmcsa.dot.gov/', 230),
('c0333333-0000-4000-8000-000000000013', 'US', 'driver', 'CDLIS_CHECK', 'CDLIS driver history check', 'recommended', 'screening', 0, 0,
 'At hire', 'Driver holds or held a commercial driver''s license',
 'Finds every State that has licensed the driver, so the MVR inquiries reach all of them.',
 NULL, 'AAMVA / FMCSA', 'https://www.fmcsa.dot.gov/registration/commercial-drivers-license/cdlis', 240),
('c0333333-0000-4000-8000-000000000014', 'US', 'driver', 'CRIMINAL_BACKGROUND', 'Criminal background check', 'recommended', 'screening', 1, 0,
 'At hire, then on the broker''s or State''s recheck cycle', '',
 'No federal rule sets this for NEMT drivers; broker contracts and State law almost always do, and several States require fingerprint-based screening.',
 NULL, 'Broker and State contracts', NULL, 260);
