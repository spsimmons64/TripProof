-- ################################################################################################
-- # 207 - the drug and alcohol policy names its DER, and the signed copy keeps what it said.
-- #
-- # 49 CFR 382.601 wants the policy to name the person who answers questions about the program, and
-- # 382.105 wants a Designated Employer Representative. Both are the same person and TripProof now
-- # knows who they are - the appointment lives in companyroles. So the policy fills itself in: the
-- # company's name, its effective date, the discipline the company chose, and the DER's name, title,
-- # telephone and email.
-- #
-- # The important half is the second one. A document whose blanks are filled from live data cannot
-- # be reproduced once the data moves: appoint a new DER in June and every copy a driver signed in
-- # March would name the wrong person, which is worse than naming nobody. So the FILLED text is
-- # stored with the signature. The hash already proved the words; now the words are there to be
-- # read back, exactly as that driver saw them.
-- #
-- # Two things are genuinely the company's own and cannot be derived: the day the policy took
-- # effect, and which consequence the company adopts under its own authority at section 10. They
-- # are a date and a choice of three - not a text editor, which would leave every customer with
-- # bespoke legal wording nobody can version or correct.
-- ################################################################################################

ALTER TABLE accounts
  ADD COLUMN IF NOT EXISTS dapolicyeffective  DATE        NULL,
  ADD COLUMN IF NOT EXISTS dapolicydiscipline VARCHAR(16) NULL,
  ADD COLUMN IF NOT EXISTS dapolicyother      VARCHAR(300) NULL;

ALTER TABLE documentsignatures
  ADD COLUMN IF NOT EXISTS signedtext LONGTEXT NULL AFTER contentversion;
