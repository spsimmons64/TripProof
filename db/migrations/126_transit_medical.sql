-- ################################################################################################
-- # 126 - the bus transit medical is an examination with a result, not a file somebody uploaded.
-- #
-- # FDOT Form 725-030-11 under F.A.C. 14-90.0041 ends in a determination the examiner makes, and
-- # that determination is the whole compliance question:
-- #
-- #     MEETS STANDARDS - RE-EXAMINE IN 2 YEARS          qualified, two years
-- #     MEETS STANDARDS, PERIODIC EVALUATION REQUIRED    qualified, until the date the examiner set
-- #     DOES NOT MEET STANDARDS                          not qualified
-- #
-- # Kept as an upload, none of that is readable: the file expires on the rule's own two-year clock
-- # whatever the examiner wrote, a driver qualified for six months reads as qualified for two years,
-- # and a driver who did not meet the standards reads as compliant because a document is on file.
-- # So the result is a column, and the date the examiner qualified them through is a column.
-- #
-- # WHAT IS DELIBERATELY NOT HERE
-- #
-- # The form also carries a long health history - seizures, heart disease, psychiatric conditions,
-- # diabetes - and the examination findings behind it. None of that is stored. Under the rule the
-- # examiner keeps the complete examination; what the transit system keeps is the certification.
-- # Holding a driver's medical history would be more sensitive data than the compliance question
-- # needs, kept by an employer who has no reason to read it, so the columns for it do not exist and
-- # cannot be filled in later by accident.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS transitmedicals (
    recordid         VARCHAR(36) NOT NULL,
    accountid        VARCHAR(36) NOT NULL,
    driverid         VARCHAR(36) NOT NULL,

    -- Which of the four occasions the rule recognises. 14-90.0041 asks for one before employment,
    -- one at least every two years, and one back after 30+ days off ill or injured, so the occasion
    -- is part of the record rather than something inferred from its date.
    examtype         VARCHAR(16) NOT NULL,      -- preemployment | biennial | followup | returntoduty
    examinedon       DATE        NOT NULL,

    -- Who made the determination. The certificate names them, and a determination with nobody
    -- behind it is not one.
    examinername     VARCHAR(120) NULL,
    examinerlicense  VARCHAR(60)  NULL,
    examinerstate    VARCHAR(2)   NULL,
    examinertype     VARCHAR(8)   NULL,         -- MD | DO | PA | ARNP

    -- The determination, and how long it stands. `qualifiedthrough` is the examiner's date, not a
    -- sum done here: an examiner who qualified somebody for six months said six months.
    result           VARCHAR(16) NOT NULL,      -- meets | meetsperiodic | doesnotmeet
    qualifiedthrough DATE        NULL,

    correctivelenses TINYINT(1)  NOT NULL DEFAULT 0,
    hearingaid       TINYINT(1)  NOT NULL DEFAULT 0,
    otherrestriction VARCHAR(255) NULL,

    -- Temporarily disqualified is not a lesser kind of qualified. While it stands the driver does
    -- not drive, whatever the certificate's own dates say.
    tempdisqualified TINYINT(1)  NOT NULL DEFAULT 0,
    tempreason       VARCHAR(255) NULL,
    followupon       DATE        NULL,

    documentid       VARCHAR(36) NULL,
    createdon        DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    createdby        VARCHAR(36) NULL,
    deleted          DATETIME    NULL,
    PRIMARY KEY (recordid),
    KEY ix_transitmedicals_driver (accountid, driverid, examinedon)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The rule now reads the examination rather than a credential filed under its name.
UPDATE compliancerules
   SET evidencesource = 'transitmedical'
 WHERE code = 'FL_TRANSIT_MEDICAL' AND subject = 'driver';
