-- The exposure determination is made here, not ticked somewhere else.
--
-- 29 CFR 1910.1030(c)(2) asks an employer to work out which job classifications have
-- occupational exposure to blood, write that down, and keep it current. Until now the fact the
-- engine used - company.exposure - was a yes/no question on the applicability screen, and the
-- document that OSHA actually asks for was a published sheet with a ruled blank where the
-- answer goes. Two copies of one thing, and the one that satisfies the section was the empty
-- one.
--
-- So the determination becomes a record: the classifications, the answer, and a signature from
-- the person certifying it. company.exposure is then read FROM that record, and the question
-- is retired - there is one answer and it is the one on the signed page.

CREATE TABLE IF NOT EXISTS exposuredeterminations (
  recordid        VARCHAR(36)  NOT NULL,
  accountid       VARCHAR(36)  NOT NULL,
  assessedon      DATE         NOT NULL,
  -- Section 7. The whole point of the exercise, and the fact every driver's training hangs on.
  exposed         TINYINT(1)   NOT NULL,
  nextreview      DATE             NULL,
  changes         VARCHAR(512)     NULL,
  corrective      VARCHAR(512)     NULL,
  -- A determination filed against the wrong account, or simply wrong, is withdrawn rather than
  -- deleted: what was determined and when is the question an inspector asks.
  withdrawn       DATETIME         NULL,
  withdrawnby     VARCHAR(36)      NULL,
  addedby         VARCHAR(36)  NOT NULL,
  added           DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
  PRIMARY KEY (recordid),
  KEY ix_exposuredeterminations_account (accountid, withdrawn, assessedon),
  CONSTRAINT fk_exposuredeterminations_account
    FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Sections 3, 4 and 5 - all exposed, some exposed, none exposed. Rows rather than a block of
-- typing, because "which classifications did you say were exposed" is a question somebody will
-- ask of this record later, and prose cannot answer it.
CREATE TABLE IF NOT EXISTS exposureclassifications (
  recordid        VARCHAR(36)  NOT NULL,
  accountid       VARCHAR(36)  NOT NULL,
  determinationid VARCHAR(36)  NOT NULL,
  band            VARCHAR(8)   NOT NULL,          -- all | some | none
  classification  VARCHAR(160) NOT NULL,
  detail          VARCHAR(512)     NULL,
  sortorder       INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (recordid),
  KEY ix_exposureclassifications_det (determinationid, band, sortorder),
  CONSTRAINT fk_exposureclassifications_det
    FOREIGN KEY (determinationid) REFERENCES exposuredeterminations (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The question stops being asked. Its answer is now made on the determination, and leaving it
-- on the applicability screen would leave two places to say one thing.
UPDATE companyquestions SET active = 0 WHERE code = 'EXPOSURE_DUTIES';

-- The determination is owed whether or not there is exposure.
--
-- It was gated on company.exposure being true, which is backwards: the determination is what
-- SETTLES that fact. A company that answered no owed nothing and had nothing written down,
-- when 1910.1030(c)(2) wants the determination either way - "we looked, and these duties do
-- not involve exposure" is a determination, and it is the one an inspector asks to see from a
-- carrier claiming the section does not reach it.
UPDATE compliancerules SET applieswhen = NULL
 WHERE code = 'BBP_EXPOSURE_DETERMINATION';

-- It is no longer answered by adopting a policy. The policy is the WORDING; the evidence is a
-- determination somebody made and signed on it.
UPDATE compliancerules
   SET evidencekind   = 'determination',
       evidencesource = 'exposuredetermination',
       recurrence     = 'ondocument'
 WHERE code = 'BBP_EXPOSURE_DETERMINATION';
