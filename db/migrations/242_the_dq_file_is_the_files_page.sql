-- The driver qualification file is a PLACE, not a requirement.
--
-- DQ_FILE sat on the requirements list as a rollup of everything under 49 CFR 391 - a row whose
-- only content was the state of the rows above it. Every requirement it summarised is already
-- on that list in its own right, and the file it describes is already a screen: Driver Files.
-- So it told nobody anything they could not see, and had nothing to click.
--
-- 49 CFR 391.51 is not dropped as an obligation. It says what the file must contain, and what
-- the file contains is every one of those requirements, each asked and answered individually.
-- The summary row was the only thing removed.

UPDATE compliancerules
   SET effectiveto = CURDATE(),
       note = 'Retired. A rollup of the other 49 CFR 391 requirements, all of which are asked '
              'individually, over a file that is already its own screen (Driver Files).'
 WHERE code = 'DQ_FILE';
