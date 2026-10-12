-- The exposure determination asks about duties, not job titles.
--
-- It was built as three tables of job classifications somebody typed in. That is what the OSHA
-- form looks like on paper, and it is the wrong shape for this product: everywhere else in
-- TripProof you pick something the system already knows - a driver, a user, a vehicle - and act
-- on it. Asking a dispatcher to invent a job-title taxonomy is a compliance officer's task on a
-- screen built for somebody with a phone ringing.
--
-- What 1910.1030(c)(2) actually turns on is narrow, and the regulation names it: does anybody
-- here, as part of their assigned work, do first aid, clean up blood, handle contaminated
-- sharps or materials, or assist a passenger where contact is reasonably anticipated. Those are
-- the ticks. The answer follows from them - any duty ticked is exposure, none ticked is not -
-- so the yes/no question goes too, and with it the chance of ticking a duty and then answering
-- "no occupational exposure" beside it.
--
-- The classifications table is dropped rather than migrated because nothing has been determined
-- yet: it has never held a row on any account.

DROP TABLE IF EXISTS exposureclassifications;

CREATE TABLE IF NOT EXISTS exposureduties (
  recordid        VARCHAR(36) NOT NULL,
  accountid       VARCHAR(36) NOT NULL,
  determinationid VARCHAR(36) NOT NULL,
  -- One of the duties app/exposure.py names. Stored as the key rather than the sentence, so
  -- the wording can be corrected without rewriting what companies have determined.
  duty            VARCHAR(32) NOT NULL,
  PRIMARY KEY (recordid),
  UNIQUE KEY ux_exposureduties_once (determinationid, duty),
  CONSTRAINT fk_exposureduties_det
    FOREIGN KEY (determinationid) REFERENCES exposuredeterminations (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
