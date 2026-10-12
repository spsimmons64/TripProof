-- ################################################################################################
-- # 108 - interstate becomes a question like the others.
-- #
-- # It arrived in 105 as a column on `accounts`, before there was anywhere better to put it. 107
-- # then built the proper home - companyquestions and companyanswers - and left interstate behind,
-- # which produced exactly the failure the rest of this work is meant to prevent: one fact held in
-- # two kinds of place, behaving two different ways.
-- #
-- # On screen that read as a straightforward bug. The six questions save the moment you answer
-- # them; interstate sat in the profile form above and needed the Save button. Two controls that
-- # look identical, one of which silently discards your answer. The account had all six questions
-- # answered and interstate still NULL, and every Part 391 rule was reporting itself undecidable
-- # while the office had already answered the question.
-- #
-- # So the column goes. One mechanism, one place, one behaviour.
-- ################################################################################################

INSERT INTO companyquestions (code, factname, question, help, sortorder)
SELECT 'INTERSTATE', 'operation.interstate',
       'Do you ever drive across a state line?',
       'This decides whether the federal safety regulations reach you at all - 49 CFR 390.3T(a)(1) applies them to interstate commerce. Florida re-applies a frozen copy of them to intrastate operation on its own terms and then exempts most NEMT vehicles from it, so the same van owes different things on each side of the line.',
       5
WHERE NOT EXISTS (SELECT 1 FROM companyquestions WHERE code = 'INTERSTATE');

-- Carry across anything already answered, so nobody is asked twice.
INSERT INTO companyanswers (accountid, code, answer, updated)
SELECT recordid, 'INTERSTATE', interstate, COALESCE(updated, CURRENT_TIMESTAMP)
  FROM accounts WHERE interstate IS NOT NULL
ON DUPLICATE KEY UPDATE answer = VALUES(answer);

-- And the second home for the fact goes, so it cannot drift again.
ALTER TABLE accounts DROP COLUMN IF EXISTS interstate;
