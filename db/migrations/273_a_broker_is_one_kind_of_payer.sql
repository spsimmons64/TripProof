-- A broker is one kind of payer.
--
-- `brokers` held the only payer this product could name, because every trip it had ever seen
-- came from one. That is no longer true: a company may bill Medicaid direct, a Medicare
-- Advantage plan, a commercial insurer, a workers' compensation carrier, a facility it has a
-- contract with, or the passenger. Modivcare is not a different sort of thing from Aetna -
-- it is the same thing with a different category and a different place to send the bill.
--
-- So the table is RENAMED rather than joined by a second one. Two tables that both mean
-- "who pays" would drift the first time somebody added a payer to the wrong one, and the
-- foreign keys from `trips` and `rulesets` follow a rename without being touched.
--
-- What is NOT here: plans, contracts, coverage, authorisations, claims. Those come when
-- there is something to bill. This is the one change that gets expensive later, because
-- nothing has been priced yet.

-- Guarded: a half-applied file is re-run from the top, and RENAME is not repeatable.
SET @renaming := (SELECT COUNT(*) FROM information_schema.TABLES
                  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'brokers');
SET @sql := IF(@renaming > 0, 'RENAME TABLE brokers TO payers', 'DO 0');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

ALTER TABLE payers
  -- medicaid | medicare_advantage | commercial | workers_comp | auto_pip | va | facility
  -- | broker | private
  --
  -- What kind of payer this is, which decides what billing it can support - a Medicaid
  -- programme can take a claim, a broker takes its own submission, a facility takes an
  -- invoice. Everything already here is a broker, which is what the default says.
  ADD COLUMN IF NOT EXISTS category VARCHAR(24) NOT NULL DEFAULT 'broker' AFTER name,
  -- NULL means every company can use it: Modivcare and Aetna are the same organisation
  -- whoever is billing them. A company's own facility contracts are its own, so they carry
  -- the account that added them and nobody else sees them.
  ADD COLUMN IF NOT EXISTS accountid VARCHAR(36) NULL AFTER recordid,
  -- How the clearinghouse names this payer. Not our code and not their name - Claim.MD
  -- identifies a payer by its own id, and a claim sent with the wrong one is rejected at the
  -- front door. Nullable because a broker or a facility is not billed electronically at all.
  ADD COLUMN IF NOT EXISTS payerid VARCHAR(24) NULL;

-- The code was unique across the whole table while every row was a broker everyone shared.
-- A company adding "ST JOSEPHS" must not be blocked because another company already did, so
-- uniqueness is per owner, with the platform catalogue as one owner among them.
ALTER TABLE payers DROP INDEX IF EXISTS ux_brokers_code;
ALTER TABLE payers ADD UNIQUE KEY IF NOT EXISTS ux_payers_code (accountid, code);

ALTER TABLE payerschedules
  -- Whose rates these are.
  ADD COLUMN IF NOT EXISTS payerid VARCHAR(36) NULL AFTER payer,
  -- And who receives the bill, when that is somebody else. The insurance company on a
  -- passenger's card is frequently not the organisation the claim goes to: a Medicare
  -- Advantage plan may route its transport through Modivcare, and the money comes from the
  -- plan while the paperwork goes to the broker. NULL means the payer bills itself, which is
  -- the ordinary case and should not have to be stated.
  ADD COLUMN IF NOT EXISTS billtoid VARCHAR(36) NULL AFTER payerid;

-- Guarded on the column still being there: this file is re-run from the top after a failure,
-- and by then the backfill has happened and brokerid has gone.
SET @hasbrokerid := (SELECT COUNT(*) FROM information_schema.COLUMNS
                     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'payerschedules'
                       AND COLUMN_NAME = 'brokerid');
SET @sql := IF(@hasbrokerid > 0,
  'UPDATE payerschedules SET payerid = brokerid WHERE payerid IS NULL AND brokerid IS NOT NULL',
  'DO 0');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Backfilled, so the old column is removed rather than left beside the new one. Two columns
-- meaning "who pays" on the same row is the drift this migration exists to stop. It carries
-- no foreign key of its own, so nothing is broken by dropping it.
ALTER TABLE payerschedules DROP COLUMN IF EXISTS brokerid;

-- MariaDB has no IF NOT EXISTS for ADD CONSTRAINT ... FOREIGN KEY, so each one is asked for
-- only when it is absent. The same shape as the rename above, and for the same reason.
SET @fk := (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_payers_account');
SET @sql := IF(@fk = 0, 'ALTER TABLE payers ADD CONSTRAINT fk_payers_account
                         FOREIGN KEY (accountid) REFERENCES accounts (recordid)', 'DO 0');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @fk := (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_payerschedules_payer');
SET @sql := IF(@fk = 0, 'ALTER TABLE payerschedules ADD CONSTRAINT fk_payerschedules_payer
                         FOREIGN KEY (payerid) REFERENCES payers (recordid)', 'DO 0');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @fk := (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_payerschedules_billto');
SET @sql := IF(@fk = 0, 'ALTER TABLE payerschedules ADD CONSTRAINT fk_payerschedules_billto
                         FOREIGN KEY (billtoid) REFERENCES payers (recordid)', 'DO 0');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- And `payer` goes with it. It held private | medicaid | broker, derived from how a schedule
-- was billed and whether it named a broker - a question the payer now answers directly: no
-- payer means the passenger, and any other answer is the category on the payer's own row.
-- Keeping it would be a third place for the same fact, free to disagree with the other two.
ALTER TABLE payerschedules DROP COLUMN IF EXISTS payer;
