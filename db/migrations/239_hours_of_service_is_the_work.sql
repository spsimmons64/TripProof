-- Hours of service is the work, not a document about the work.
--
-- FL_HOURS_OF_SERVICE asked the driver to upload a "Duty status record". FDOT issues no such
-- form and asks for none. F.A.C. 14-90.006(3) and (5) set limits on what a driver may actually
-- do, and FDOT's guidance is to review the driver's schedules and work records to see whether
-- those limits were kept. A PDF on a file does not answer that question; the work does.
--
-- So the requirement now reads duty records - a row per driver per day - and the engine checks
-- the three limits over them. Nothing is uploaded for it any more.
--
-- The name also carried its own specification inside it, "(12 h driving, 16 h duty, 72 h/7
-- days)", which wrapped every list it appeared on. Those numbers belong in the description and
-- in the sentence the rule gives back when a limit is broken, where they can be read.

CREATE TABLE IF NOT EXISTS driverdutydays (
  recordid        CHAR(36)     NOT NULL PRIMARY KEY,
  accountid       CHAR(36)     NOT NULL,
  driverid        CHAR(36)     NOT NULL,
  dutydate        DATE         NOT NULL,
  -- When the day started and ended, where it is known. The totals are what the limits are
  -- measured against; these are what makes the record readable by somebody checking it.
  dutystart       TIME         NULL,
  dutyend         TIME         NULL,
  drivingminutes  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  ondutyminutes   SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  -- Where the numbers came from. A limit that counts only the work TripProof happens to know
  -- about is not a limit, so work done outside the trip workflow is entered by hand and says so.
  source          VARCHAR(12)  NOT NULL DEFAULT 'manual',
  note            VARCHAR(255) NULL,
  enteredby       CHAR(36)     NULL,
  added           DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
  updated         DATETIME     NULL,
  deleted         DATETIME     NULL,
  UNIQUE KEY uq_dutyday (accountid, driverid, dutydate),
  KEY ix_dutyday_driver (accountid, driverid, dutydate)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

UPDATE compliancerules
   SET name = 'Driver hours of service record',
       description = CONCAT(
         'The driver''s actual work, day by day, against the limits in F.A.C. 14-90.006: no ',
         'more than 12 hours driving in a 24-hour period, no driving after 16 hours on duty in ',
         'a 24-hour period, and no more than 72 hours on duty in any 7 consecutive days. The ',
         'seven-day limit rolls - every day is the end of its own window - so a driver can keep ',
         'each calendar week under 72 hours and still break it across a weekend. Nothing is ',
         'uploaded: the record is the duty days held against the driver, and work done outside ',
         'the trip workflow is entered by hand.'),
       evidencekind = 'process',
       evidencesource = 'dutyhours',
       duetext = 'Kept day by day, for as long as the driver works'
 WHERE code = 'FL_HOURS_OF_SERVICE';

-- Nothing was ever filed against it, and nothing should be.
UPDATE credentialtypes SET active = 0 WHERE code = 'DUTY_STATUS_RECORD';
