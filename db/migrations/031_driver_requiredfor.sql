-- ################################################################################################
-- # 031 - driver documents answer one question instead of three: who is it required for?
-- #
-- # requiredfor  'both'    every driver, CDL or not
-- #              'cdl'     CDL drivers only
-- #              'noncdl'  non-CDL drivers only
-- #              'none'    not required by law - broker contract, insurer or good practice
-- #
-- # This replaces required / conditional / recommended on the Driver Compliance page. The company
-- # catalog keeps its three buckets; requiredfor is null there.
-- #
-- # The six part 391 rows (driver qualification file, MVRs, safety performance history, medical
-- # certificate, road test) are marked 'cdl'. Strictly they follow the vehicle, not the licence: a
-- # 9-to-15 passenger van carrying passengers for compensation across State lines is a commercial
-- # motor vehicle whose driver needs no CDL. Each row's appliesif still states that real trigger.
-- ################################################################################################
ALTER TABLE compliancedocs
    ADD COLUMN IF NOT EXISTS requiredfor VARCHAR(8) NULL AFTER obligation;

ALTER TABLE compliancedocs
    ADD CONSTRAINT IF NOT EXISTS ck_compliancedocs_requiredfor
        CHECK (requiredfor IS NULL OR requiredfor IN ('both', 'cdl', 'noncdl', 'none'));

-- Everything a driver needs whatever they drive.
UPDATE compliancedocs SET requiredfor = 'both' WHERE subject = 'driver';

-- CDL only: part 382 (drug and alcohol testing, Clearinghouse) and part 391 (the commercial file).
UPDATE compliancedocs SET requiredfor = 'cdl' WHERE subject = 'driver' AND code IN (
    'DA_POLICY_RECEIPT', 'CLEARINGHOUSE_CONSENT', 'PREEMPLOYMENT_DRUG_TEST', 'CLEARINGHOUSE_PREEMP',
    'RANDOM_TESTING_RECORDS', 'CLEARINGHOUSE',
    'DQ_FILE', 'MVR_PREEMPLOYMENT', 'MVR_ANNUAL', 'SAFETY_PERFORMANCE_HISTORY', 'MEDICAL_CERT', 'ROAD_TEST');

-- Below the CDL line this is the drug screen a broker or State asks for instead of part 382.
UPDATE compliancedocs SET requiredfor = 'noncdl' WHERE subject = 'driver' AND code = 'DRUG_SCREEN_NONCDL';

-- Not law: broker contracts, insurers, good practice.
UPDATE compliancedocs SET requiredfor = 'none'
    WHERE subject = 'driver' AND obligation = 'recommended' AND code <> 'DRUG_SCREEN_NONCDL';

-- Keep the old bucket consistent with the new field, so nothing reads a stale value.
UPDATE compliancedocs SET obligation = 'recommended' WHERE subject = 'driver' AND requiredfor = 'none';
UPDATE compliancedocs SET obligation = 'required' WHERE subject = 'driver' AND requiredfor = 'both';
UPDATE compliancedocs SET obligation = 'conditional' WHERE subject = 'driver' AND requiredfor IN ('cdl', 'noncdl');
