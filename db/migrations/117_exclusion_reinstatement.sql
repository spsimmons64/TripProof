-- ################################################################################################
-- # 117 - lifting an exclusion.
-- #
-- # 116 made a confirmed exclusion outrank everything after it, which is right - the monthly job
-- # writes a clear row every month and none of them can undo a person having checked the SSN and
-- # said yes. But it left no way out. A driver who is reinstated by OIG stayed red forever.
-- #
-- # WHY THIS IS AN EVENT WITH A DOCUMENT, NOT A FLAG SOMEBODY TOGGLES
-- #
-- # An OIG exclusion does not expire. The excluded person has to apply for reinstatement and OIG
-- # issues a written notice granting it - so there is always a piece of paper, and requiring it is
-- # not bureaucracy, it is the only thing that distinguishes a reinstatement from somebody deciding
-- # they would rather the red mark went away.
-- #
-- # AND IT MUST NOT BE INFERRED FROM THE LIST
-- #
-- # The tempting shortcut is to lift the flag when the driver stops appearing in next month's file.
-- # That is wrong. Our match is name plus date of birth; the CONFIRMATION came from an SSN check on
-- # OIG's own form. Absence from a name match is not evidence that this person was reinstated - it
-- # could be a corrected spelling, a changed record, or our match having been wrong to begin with.
-- # So the job never lifts anything, and a disappearance is at most something to tell somebody about.
-- #
-- # The confirmed row is kept and marked, never deleted. What the file held on the day a trip ran is
-- # the question an auditor asks, and a record that quietly became clean cannot answer it.
-- ################################################################################################

ALTER TABLE exclusionchecks
    ADD COLUMN IF NOT EXISTS liftedon    DATE         NULL AFTER verifymethod,
    ADD COLUMN IF NOT EXISTS liftedby    VARCHAR(36)  NULL AFTER liftedon,
    ADD COLUMN IF NOT EXISTS liftreason  VARCHAR(512) NULL AFTER liftedby,
    ADD COLUMN IF NOT EXISTS liftdocid   VARCHAR(36)  NULL AFTER liftreason;
