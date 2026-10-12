-- ################################################################################################
-- # 167 - the good faith effort as a document somebody signs, not a note somebody typed.
-- #
-- # 49 CFR 391.23(i) says the carrier must document a good faith effort to obtain the information
-- # and that the previous employer's silence does not relieve the obligation. What an auditor asks
-- # for is therefore not "did they answer" but "what did you do, and who says so".
-- #
-- # Two things were missing.
-- #
-- #   THE OUTCOME, in its own words. "Closed" ran together five different endings: records came
-- #   back, nobody answered, the employer could not produce them, the employer no longer exists,
-- #   and still working on it. A file that says "good faith effort documented - prior employer did
-- #   not respond" is a different record from one that says the history was received, and the two
-- #   must never read the same.
-- #
-- #   THE SIGNATURE. Somebody certifies that the attempts on file are what was actually done. It is
-- #   the signer's signature of record - adopted once behind a date of birth and a Social Security
-- #   number, and applied here the same way it is applied to the request itself. Nobody types their
-- #   name into this form.
-- ################################################################################################

ALTER TABLE employerinquiries
    ADD COLUMN IF NOT EXISTS effortstatus      VARCHAR(24) NULL AFTER effortnote,
    ADD COLUMN IF NOT EXISTS effortsignature   VARCHAR(160) NULL AFTER effortstatus,
    ADD COLUMN IF NOT EXISTS effortsignatureid VARCHAR(36) NULL AFTER effortsignature,
    ADD COLUMN IF NOT EXISTS effortfontkey     VARCHAR(24) NULL AFTER effortsignatureid,
    ADD COLUMN IF NOT EXISTS effortsignedon    DATETIME    NULL AFTER effortfontkey;
