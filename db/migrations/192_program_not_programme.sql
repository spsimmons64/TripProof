-- ################################################################################################
-- # 192 - program, not programme.
-- #
-- # This is American software quoting American regulations to American operators, and the British
-- # spelling had got into rule names, citations, notes and one of the company questions. Swept out
-- # of the source in the same change; this is for the text that lives in the database.
-- #
-- # The migrations that wrote it are left exactly as they are. An applied migration is a record of
-- # what ran, not a document to go back and tidy - and this one runs after them on a fresh database
-- # just as it does on an old one, so the end state is the same either way.
-- ################################################################################################

UPDATE compliancerules
   SET name     = REPLACE(REPLACE(name, 'programme', 'program'), 'Programme', 'Program'),
       citation = REPLACE(REPLACE(citation, 'programme', 'program'), 'Programme', 'Program'),
       note     = REPLACE(REPLACE(note, 'programme', 'program'), 'Programme', 'Program')
 WHERE name LIKE '%rogramme%' OR citation LIKE '%rogramme%' OR note LIKE '%rogramme%';

UPDATE companyquestions
   SET question = REPLACE(REPLACE(question, 'programme', 'program'), 'Programme', 'Program'),
       help     = REPLACE(REPLACE(help, 'programme', 'program'), 'Programme', 'Program')
 WHERE question LIKE '%rogramme%' OR help LIKE '%rogramme%';

UPDATE credentialtypes
   SET name = REPLACE(REPLACE(name, 'programme', 'program'), 'Programme', 'Program')
 WHERE name LIKE '%rogramme%';
