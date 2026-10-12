-- One requirement for one body of training, and the testing Florida actually asks for.
--
-- THREE RULES WERE ASKING THE SAME QUESTION. All three fired on the same trigger - the fleet
-- carries wheelchairs - and all three were about 49 CFR 37.173 proficiency:
--
--   ADA_PROFICIENCY           "Passenger assistance and equipment proficiency"          no citation
--   PASS_TRAINING             "Passenger assistance and equipment proficiency training" 49 CFR 37.173
--   SECUREMENT_TRAINING_CERT  "Wheelchair securement training certificate"              49 CFR 37.173
--
-- A driver could be satisfied on one and outstanding on the other two for the same training, and
-- an office reading that list had no way to tell what the difference was meant to be - because
-- there was none. The regulation describes a single duty: the driver must be trained to
-- proficiency in operating the accessibility equipment AND in assisting the people who use it.
-- 37.165 says what they must be proficient at; 37.173 says they must be. One rule.
--
-- TRAINING IS NOT TESTING. F.A.C. 14-90.004(3)(d) asks for training AND testing demonstrating
-- adequate skills before the driver operates the applicable vehicle unsupervised. A requirement
-- that turns green because somebody uploaded a PDF with "certificate" in the filename has not
-- checked the thing Florida asks about. So the record carries two facts - trained, and tested -
-- and the requirement is not answered until it carries both.

-- 1. The record gains the second fact. On the credential rather than in a table of its own: it is
--    the same event, recorded by the same person, about the same driver.
ALTER TABLE credentials
  ADD COLUMN testedon DATE NULL AFTER issuedon,
  ADD COLUMN testedby VARCHAR(128) NULL AFTER testedon;

-- 2. Which kinds of record are not complete without it. A flag on the TYPE, so the engine asks
--    the question of every credential of that kind rather than naming one rule in code.
ALTER TABLE credentialtypes
  ADD COLUMN requirestesting TINYINT(1) NOT NULL DEFAULT 0 AFTER maxagedays;

UPDATE credentialtypes
   SET name = 'Passenger assistance and wheelchair securement training',
       requirestesting = 1
 WHERE code = 'WHEELCHAIR_SECUREMENT';

-- 3. Everything already filed against the two retired codes is the same training, so it moves
--    across rather than being stranded. A driver who was proficient yesterday is proficient
--    today, and a merge that quietly made people non-compliant would be a worse answer than
--    leaving the duplicates alone.
UPDATE credentials
   SET credentialtypeid = (SELECT recordid FROM credentialtypes WHERE code = 'WHEELCHAIR_SECUREMENT')
 WHERE credentialtypeid IN (SELECT recordid FROM (
         SELECT recordid FROM credentialtypes WHERE code IN ('ADA_PROFICIENCY', 'PASSENGER_ASSIST')
       ) AS t)
   AND deleted IS NULL;

-- Carried-over records were never tested here, so they say so rather than claiming they were.
-- The office can record the testing; nothing pretends it already happened.

-- 4. The one rule that remains.
UPDATE compliancerules
   SET name = 'Passenger assistance and wheelchair securement training'
 WHERE code = 'SECUREMENT_TRAINING_CERT';

-- 5. The two that were asking it over again. Closed rather than deleted: a file read next year
--    has to show what was asked of a driver at the time, and a rule that vanishes takes its own
--    history with it.
UPDATE compliancerules
   SET effectiveto = CURDATE(),
       note = 'Retired. Merged into SECUREMENT_TRAINING_CERT, which asks for the same training '
              'under 49 CFR 37.165 and 37.173.'
 WHERE code IN ('ADA_PROFICIENCY', 'PASS_TRAINING');

UPDATE credentialtypes SET active = 0
 WHERE code IN ('ADA_PROFICIENCY', 'PASSENGER_ASSIST');
