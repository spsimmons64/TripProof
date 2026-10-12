-- ################################################################################################
-- # 052 - the usual period, as a number.
-- #
-- # The catalog already said how often each thing comes round, in words: "At least once every 12
-- # months", "Monthly", "two years is common". Words are right for the page and useless for a date,
-- # so each of them gets the number that sentence means. An account still sets its own - a broker
-- # that wants an MVR every six months overrides it - but nobody has to type a figure the rule
-- # already states.
-- #
-- # Where the copy prints its own date, there is no period: a driver's license expires when the
-- # license says it does, not a year after it was filed.
-- ################################################################################################
ALTER TABLE compliancedocs ADD COLUMN validdays INT NULL AFTER expires;

UPDATE compliancedocs SET validdays = CASE code
    WHEN 'FL_TRANSIT_MEDICAL'       THEN 730    -- at least every 2 years
    WHEN 'FL_LEVEL2_DRIVER'         THEN 1825   -- 5-year renewal basis
    WHEN 'MVR_FILE'                 THEN 365    -- at hire, then the company's cycle
    WHEN 'EXCLUSION_CHECK_DRIVER'   THEN 31     -- monthly
    WHEN 'PASS_TRAINING'            THEN 730    -- two years is common
    WHEN 'HIPAA_TRAINING_DRIVER'    THEN 365    -- annual is the common practice
    WHEN 'MVR_ANNUAL'               THEN 365    -- at least once every 12 months
    WHEN 'MEDICAL_CERT'             THEN 730    -- at most every 24 months
    WHEN 'SECUREMENT_TRAINING_CERT' THEN 730    -- two years is common
    WHEN 'BBP_TRAINING'             THEN 365    -- at least annually
    WHEN 'CLEARINGHOUSE'            THEN 365    -- annually for every CDL driver
    WHEN 'CRIMINAL_BACKGROUND'      THEN 365    -- at hire, then the broker's or State's cycle
    WHEN 'SEX_OFFENDER_CHECK'       THEN 365
    WHEN 'ABUSE_REGISTRY_CHECK'     THEN 365
    WHEN 'CPR_FIRST_AID'            THEN 730    -- two years is common
    WHEN 'DEFENSIVE_DRIVING'        THEN 1095   -- three years is common
    ELSE validdays END
WHERE subject = 'driver' AND expires = 1;
-- DRIVER_LICENSE_COPY is deliberately left without one: the licence carries its own expiry date.

-- Accounts that have not set their own period take the catalog's.
UPDATE accountqualifications q
  JOIN compliancedocs c ON c.code = q.code AND c.subject = 'driver'
   SET q.validdays = c.validdays
 WHERE q.catalog = 1 AND q.validdays IS NULL AND c.validdays IS NOT NULL;
