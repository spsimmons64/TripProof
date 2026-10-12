-- ################################################################################################
-- # 187 - a query run before the violation cannot answer the question.
-- #
-- # 186's predecessor wrote a Clearinghouse record saying "prohibited" whenever a violation was
-- # recorded, so that the office would be made to run a fresh query before requalifying anybody.
-- # It worked, and it was wrong: nobody ran that query. The file ended up holding a result that
-- # was reasoned rather than received, and a compliance file that reasons is a compliance file an
-- # auditor cannot trust. Removed, and the rows it wrote with it.
-- #
-- # The honest version needs no record at all, because the fact is already here. The Clearinghouse
-- # is the register OF drug and alcohol violations. A query dated before a violation was recorded
-- # cannot say anything about that violation, whatever it said on the day - so it is not a stale
-- # answer, it is an answer to a different question. The engine can see that by comparing two dates
-- # it already holds, and the requirement goes back to "run a query" on its own.
-- #
-- # What this buys, and it is the point: the drug and alcohol bar and the Clearinghouse answer stay
-- # two separate things to clear. Completing the return-to-duty process lifts the bar; it does not
-- # move the query's date, so the Clearinghouse requirement stays outstanding until somebody runs a
-- # real one. Neither releases the other, and nothing is invented to make that true.
-- ################################################################################################

ALTER TABLE compliancerules
  ADD COLUMN violationresets TINYINT(1) NOT NULL DEFAULT 0 AFTER recurrencedays;

UPDATE compliancerules
   SET violationresets = 1
 WHERE subject = 'driver' AND effectiveto IS NULL
   AND code IN ('CLEARINGHOUSE_PREEMP', 'CLEARINGHOUSE');

-- The invented rows. Recognisable by the note the old code wrote on every one of them; a query
-- somebody actually ran has a document behind it and never carried this sentence.
DELETE FROM driverreports
 WHERE code = 'CLEARINGHOUSE_PREEMP'
   AND note LIKE 'Recorded from a violation on file:%';
