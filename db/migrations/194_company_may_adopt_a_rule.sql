-- ################################################################################################
-- # 194 - what the law requires, and what the company asks on top of it.
-- #
-- # Everything in the catalog has so far answered one question: does this regulation reach this
-- # driver. That is the right question and it is not the only one. A company may require a driving
-- # record on every driver it hires, commercial or not, because a broker asks for it or because it
-- # is their own policy. Today there is nowhere to say so.
-- #
-- # The trap, and the reason this is a model rather than a wider `applieswhen`: a driving record
-- # obtained on a Class E driver is NOT a 49 CFR 391.23 record. The citation would be a lie, the
-- # consequence is different - a positive company test is an employment matter, a positive DOT
-- # test is a federal prohibition that goes to the Clearinghouse - and only one of the two stops
-- # can be waived by the people who imposed it.
-- #
-- # So a rule is not widened. It is ADOPTED, and the file says who is asking:
-- #
-- #   regulation   the condition on the rule decides, as now
-- #   alldrivers   the company asks it of everybody, whether or not the regulation reaches them
-- #   off          the company asks it only where the regulation requires it
-- #
-- # An election can never switch OFF something the law requires. Where the regulation reaches the
-- # driver the rule applies, whatever the company has said.
-- ################################################################################################

-- Whether a company may adopt this rule beyond its regulatory reach, and what to say about it.
-- `extendnote` carries the reason it cannot be adopted, or - where it can - the caveat that comes
-- with adopting it, which is usually that the obligation changes character on the way across.
ALTER TABLE compliancerules
  ADD COLUMN extendable TINYINT(1) NOT NULL DEFAULT 1 AFTER origin,
  ADD COLUMN extendnote VARCHAR(400) NULL AFTER extendable;

-- What one company has elected. Absent means `regulation`, so a company that has never opened the
-- page behaves exactly as it does today.
CREATE TABLE IF NOT EXISTS companyrulepolicy (
    accountid VARCHAR(36)  NOT NULL,
    rulecode  VARCHAR(48)  NOT NULL,
    applyto   VARCHAR(12)  NOT NULL DEFAULT 'regulation',   -- regulation | alldrivers | off
    reason    VARCHAR(200) NULL,       -- the contract or policy asking for it, named for the file
    updated   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedby VARCHAR(36)  NULL,
    PRIMARY KEY (accountid, rulecode),
    CONSTRAINT fk_companyrulepolicy_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------------------------
-- What cannot be adopted, because the system the rule reads has no record of the driver.
-- ------------------------------------------------------------------------------------------------
UPDATE compliancerules SET extendable = 0, extendnote =
  'The FMCSA Clearinghouse holds CDL and CLP holders. There is nobody to query for a driver who '
  'does not hold one.'
 WHERE subject = 'driver' AND effectiveto IS NULL
   AND code IN ('CLEARINGHOUSE_PREEMP', 'CLEARINGHOUSE', 'CLEARINGHOUSE_CONSENT');

UPDATE compliancerules SET extendable = 0, extendnote =
  'CDLIS carries commercial driving records. A non-commercial licence has no self-certification '
  'or medical certification status on it.'
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'CDL_MEDICAL_STATUS';

UPDATE compliancerules SET extendable = 0, extendnote =
  'Endorsements exist on commercial licences. A non-commercial licence carries none.'
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'LICENCE_ENDORSEMENTS';

-- ------------------------------------------------------------------------------------------------
-- What can be adopted but is a different obligation once it is.
-- ------------------------------------------------------------------------------------------------
UPDATE compliancerules SET extendnote =
  'A company may test a driver the DOT rules do not reach, but it is not a DOT test: a positive '
  'result is an employment matter rather than a federal prohibition, nothing goes to the '
  'Clearinghouse, and no SAP process is owed. Set the driver''s program to Company (non-DOT).'
 WHERE subject = 'driver' AND effectiveto IS NULL
   AND code IN ('PREEMPLOYMENT_DRUG_TEST', 'DA_POLICY_RECEIPT', 'RANDOM_TESTING_RECORDS');

UPDATE compliancerules SET extendnote =
  'You may ask the question of anybody. A driver the DOT rules never reached has no DOT violation '
  'history to disclose, so what comes back is a company record rather than a 49 CFR 40.25(j) one.'
 WHERE subject = 'driver' AND effectiveto IS NULL
   AND code IN ('PREEMP_DA_QUESTIONNAIRE', 'PRIOR_VIOLATION_RTD');

UPDATE compliancerules SET extendnote =
  'You may ask previous employers about employment and safety history. You cannot require their '
  'DOT drug and alcohol records under 391.23(e) for a driver Part 391 does not reach.'
 WHERE subject = 'driver' AND effectiveto IS NULL
   AND code IN ('SAFETY_PERFORMANCE_HISTORY', 'SAFETY_PERFORMANCE_CONSENT');

-- ------------------------------------------------------------------------------------------------
-- The one rule that was already doing this by hand.
--
-- MVR_PREEMPLOYMENT had no condition at all, so it reached every driver, and its citation said
-- "where Part 391 applies; broker or company policy otherwise" - the whole of this feature written
-- as a sentence in a citation. It now carries the regulatory condition and is adopted where a
-- company wants it more widely.
--
-- Every existing account is seeded to `alldrivers` so that nobody's requirements change under them
-- today. Turning it back to regulation-only is now a choice they can make on a screen.
-- ------------------------------------------------------------------------------------------------
UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"operation.interstate","is":true},{"fact":"driver.cmv","is":true}]}',
       citation = '49 CFR 391.23(a)(1)'
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'MVR_PREEMPLOYMENT';

INSERT IGNORE INTO companyrulepolicy (accountid, rulecode, applyto, reason)
SELECT a.recordid, 'MVR_PREEMPLOYMENT', 'alldrivers',
       'Asked of every driver, as it was before this was a choice.'
  FROM accounts a WHERE a.deleted IS NULL;
