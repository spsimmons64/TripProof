-- ################################################################################################
-- # 230 - a signing request remembers the file that came out of it.
-- #
-- # Most of what a driver signs is our wording, which is reproduced from the record. The I-9 and
-- # the W-4 are not ours: they are the government's forms, signed on the form itself, and what
-- # exists afterwards is a PDF. The signature already carries its hash; this is where the file
-- # itself hangs, so the office can open what was signed rather than a rebuild of it.
-- ################################################################################################

ALTER TABLE signingrequests
  ADD COLUMN IF NOT EXISTS documentid VARCHAR(36) NULL AFTER signedon;
