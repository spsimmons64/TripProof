-- The snapshots say it too.
--
-- 285 respelled the catalog but reached only the two lower-case forms in the frozen copies a past
-- evaluation keeps of the rule it ran against. What is left in them is the requirement code itself,
-- LICENCE_FITS_VEHICLE, in capitals - the one shape that pass missed. A snapshot that names a code
-- the catalog no longer has cannot be read back against it.

UPDATE evaluationruns
   SET rulesnapshot = REPLACE(rulesnapshot, 'LICENCE', 'LICENSE')
 WHERE rulesnapshot LIKE '%LICENCE%';
