-- A place to put a file that answers nothing.
--
-- Not every piece of paper in a driver's folder is evidence of a requirement. A letter, a note
-- from a clinic, a photograph of something - these belong in the file and nowhere in the engine,
-- and until now there was no way to put one there: everything had to be a credential, an MVR, a
-- licence or a test, so anything else was either forced into a category it did not belong in or
-- left out of the system entirely.
--
-- Made a credential TYPE rather than a new kind of record, so it inherits everything that
-- already works: it lands in Driver Files under what the office filed, it is withdrawable
-- because the office filed it, and the engine ignores it because no rule names it. A new table
-- would have had to re-earn all three.

INSERT INTO credentialtypes (recordid, accountid, code, name, subject, category, description,
                             maxagedays, defaultvaliddays, requirestesting, hasamount, active)
SELECT UUID(), NULL, 'MISCELLANEOUS', 'Miscellaneous', 'driver', 'filing',
       'A document kept in the driver''s file that answers no requirement. It does not expire '
       'and nothing is computed from it.',
       NULL, NULL, 0, 0, 1
 WHERE NOT EXISTS (SELECT 1 FROM credentialtypes WHERE code = 'MISCELLANEOUS');
