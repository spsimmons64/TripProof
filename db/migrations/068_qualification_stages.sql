-- ################################################################################################
-- # 068 - one decision per requirement, and when in a driver's life it falls due.
-- #
-- # The list had grown three overlapping controls: an obligation level, who it was required for, and
-- # a hidden condition the company was never asked about. Between them nobody could tell what their
-- # own drivers actually needed.
-- #
-- # One control now. For each requirement the company says who it applies to:
-- #
-- #   both     every driver
-- #   cdl      only drivers operating a commercial motor vehicle
-- #   noncdl   only drivers who are not
-- #   off      this company does not ask for it
-- #
-- # And every requirement says when it falls due, so the list reads in the order the work happens:
-- #
-- #   prehire  before anyone is hired - the decision waits on it
-- #   athire   once an offer is accepted - the forms that cannot be signed before it
-- #   ongoing  while they drive - the things that come round again
-- #
-- # What we advise stays in the catalog and is shown beside each one, so the company is choosing
-- # against a recommendation rather than guessing.
-- ################################################################################################
ALTER TABLE compliancedocs ADD COLUMN stage VARCHAR(8) NOT NULL DEFAULT 'prehire' AFTER category;

UPDATE compliancedocs SET stage = CASE code
    WHEN 'I9'                     THEN 'athire'
    WHEN 'W4'                     THEN 'athire'
    WHEN 'PREEMPLOYMENT_DRUG_TEST' THEN 'athire'
    WHEN 'DRUG_SCREEN_NONCDL'     THEN 'athire'
    WHEN 'ROAD_TEST'              THEN 'athire'
    WHEN 'MVR_ANNUAL'             THEN 'ongoing'
    WHEN 'RANDOM_TESTING_RECORDS' THEN 'ongoing'
    WHEN 'CLEARINGHOUSE'          THEN 'ongoing'
    WHEN 'FL_HOURS_OF_SERVICE'    THEN 'ongoing'
    WHEN 'FL_SSPP_DRIVER_RECORDS' THEN 'ongoing'
    WHEN 'DQ_FILE'                THEN 'ongoing'
    WHEN 'FL_INTRASTATE_DQ'       THEN 'ongoing'
    WHEN 'FL_TD_DRUG_TESTING'     THEN 'ongoing'
    WHEN 'EXCLUSION_CHECK_DRIVER' THEN 'prehire'
    ELSE 'prehire' END
WHERE subject = 'driver';

ALTER TABLE accountqualifications
    ADD COLUMN stage   VARCHAR(8) NOT NULL DEFAULT 'prehire' AFTER code,
    ADD COLUMN applies VARCHAR(8) NOT NULL DEFAULT 'off'     AFTER stage,
    ADD CONSTRAINT ck_accountqual_applies CHECK (applies IN ('both', 'cdl', 'noncdl', 'off'));

-- What each account starts with: what the rule plainly requires is on, for whoever it reaches; a
-- requirement that turns on a fact about the company starts off, because only they can say; and
-- anything merely recommended starts off too, to be turned on deliberately.
UPDATE accountqualifications q
  JOIN compliancedocs c ON c.code = q.code AND c.subject = 'driver'
   SET q.stage = c.stage,
       q.applies = CASE
           WHEN c.classification = 'required' THEN c.requiredfor
           WHEN c.classification = 'conditional' AND c.triggercode IS NULL
                AND c.requiredfor IN ('cdl', 'noncdl') THEN c.requiredfor
           ELSE 'off' END
 WHERE q.catalog = 1;

-- 'none' in the catalog means "reaches nobody by rule"; as a choice it reads as every driver.
UPDATE accountqualifications SET applies = 'both' WHERE applies = 'none';
