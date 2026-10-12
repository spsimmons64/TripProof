-- 49 CFR 382.305 is one obligation, so it gets one row.
--
-- There were two, and they said the same thing:
--
--   RANDOM_TESTING_PROGRAM   the programme - and its own standing is computed FROM the draws,
--                            through the `nodraws` determination, because "a programme with no
--                            selection drawn from it in the last twelve months is an enrolment,
--                            not a testing programme" is in its description already.
--   RANDOM_SELECTIONS        the draws.
--
-- Same citation, same gate, same subject. With no draws on file BOTH went red, for the same
-- reason, one above the other - a carrier reading its own requirements list was shown one fault
-- twice and could not tell whether it owed one thing or two.
--
-- That became plainly redundant when both rows started opening the same screen: the programme
-- dialog could not previously show the draws its own standing depended on, so the draws had a
-- row of their own to be reachable from. Now they are on the programme, and the second row is
-- a door into the same room.
--
-- RANDOM_SELECTIONS is retired. Nothing is lost: the draws are unchanged in randomselections,
-- the screen is unchanged, and what its description said that the programme's did not - the
-- scientifically valid method, and spreading the selections through the year - is said here.

UPDATE compliancerules
   SET description = CONCAT(
         'The employer must operate, or take part in, a random testing programme covering every ',
         'driver Part 382 reaches. It may run its own pool and selections, or enrol with a ',
         'consortium or third-party administrator - nothing requires an outside pool. Evidence ',
         'is the enrolment, or the company''s own written selection procedure. Drivers must be ',
         'selected by a scientifically valid method, at the minimum annual rates FMCSA sets, ',
         'with the selections spread reasonably through the year. This is not answered by the ',
         'paperwork alone: a programme with no selection drawn from it in the last twelve ',
         'months is an enrolment, not a testing programme.'),
       duetext = 'Drawn at the annual rate, spread reasonably through the year'
 WHERE code = 'RANDOM_TESTING_PROGRAM';

UPDATE compliancerules
   SET effectiveto = CURDATE(),
       note = 'Retired. 49 CFR 382.305 is one obligation and RANDOM_TESTING_PROGRAM carries it: '
              'its standing is computed from the draws, and the draws are recorded on it.'
 WHERE code = 'RANDOM_SELECTIONS';
