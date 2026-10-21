-- ################################################################################################
-- # 328 - a company's own contact at a shared payer.
-- #
-- # Where a broker is belongs to the master list; who this company deals with there is its own. The
-- # contact name and email are kept beside the company's status for the payer. Status may now be
-- # unsaid while a contact is kept, so it is nullable - unsaid falls back to the payer's own flag.
-- ################################################################################################

ALTER TABLE accountpayers
  MODIFY COLUMN active TINYINT(1) NULL,
  ADD COLUMN IF NOT EXISTS contactname  VARCHAR(128) NULL AFTER active,
  ADD COLUMN IF NOT EXISTS contactemail VARCHAR(128) NULL AFTER contactname;
