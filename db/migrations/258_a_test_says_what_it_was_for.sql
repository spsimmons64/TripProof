-- What a drug or alcohol test was FOR, and what it found.
--
-- 49 CFR 382.403 and Part 40 Appendix J: the carrier reports its testing to FMCSA on the MIS
-- form, and the form is two halves - Part III for controlled substances and Part IV for alcohol
-- - each broken down by the reason for the test and by what came back.
--
-- A test record said neither. It held the reason and a result, and no column anywhere said
-- whether the specimen was urine or breath. So the two halves of the form could not be told
-- apart, let alone filled: every positive was a positive of nothing in particular, and an
-- alcohol result had no concentration against it when 0.02 and 0.04 are different lines on the
-- form and different consequences in 382.505 and 382.507.
--
--   testtype   drug | alcohol. Which half of the form the test belongs on.
--   substance  which drug a verified positive was for - the form counts marijuana, cocaine,
--              PCP, amphetamines and opioids separately, and a test can be positive for more
--              than one, so it is text rather than a list of one.
--   bac        the alcohol concentration. The form bands it at 0.02 and 0.04; 382.505 puts a
--              driver off for 24 hours at 0.02 and 382.507 makes 0.04 a violation, so the
--              number is kept rather than the band - a band cannot be re-banded.
--
-- Existing rows are left NULL rather than guessed at. A report that quietly counts eight
-- unlabelled tests as controlled substances is worse than one that says eight were not
-- recorded, because only the second can be corrected.

ALTER TABLE drugtests
  ADD COLUMN IF NOT EXISTS testtype  varchar(8)   DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS substance varchar(120) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS bac       decimal(4,3) DEFAULT NULL;
