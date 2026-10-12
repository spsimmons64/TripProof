-- A schedule can price several payers.
--
-- One rate card is routinely used for a group: three facilities on the same flat contract,
-- two brokers who happened to agree the same numbers, a handful of plans on one commercial
-- rate. Holding one payer per schedule meant copying twenty rate lines for each of them and
-- then keeping the copies in step by hand - which is the drift this schema keeps being
-- rescued from.
--
-- So the link becomes a list. `payerid` on the schedule goes; `schedulepayers` carries who a
-- schedule prices, and `privatepay` carries the one payer that has no record - the passenger.
--
-- The rule that matters is unchanged and now has to hold across the list: no payer may be
-- covered by two live schedules over the same days. That is checked per payer, so a
-- renegotiating facility can be lifted onto its own schedule without disturbing the others.

ALTER TABLE payerschedules
  -- The passenger. Not a row in `payers` because there is nobody to record: no address, no
  -- payer id, no contract. A schedule either prices them or prices payers.
  ADD COLUMN IF NOT EXISTS privatepay TINYINT(1) NOT NULL DEFAULT 0 AFTER name;

CREATE TABLE IF NOT EXISTS schedulepayers (
  scheduleid VARCHAR(36) NOT NULL,
  payerid    VARCHAR(36) NOT NULL,
  -- Carried so the company's own rows can be found without joining back through the
  -- schedule, which is what the clash check does on every save.
  accountid  VARCHAR(36) NOT NULL,
  added      DATETIME    NOT NULL DEFAULT UTC_TIMESTAMP(),
  PRIMARY KEY (scheduleid, payerid),
  KEY ix_schedulepayers_payer (accountid, payerid),
  CONSTRAINT fk_schedulepayers_schedule
    FOREIGN KEY (scheduleid) REFERENCES payerschedules (recordid) ON DELETE CASCADE,
  CONSTRAINT fk_schedulepayers_payer
    FOREIGN KEY (payerid) REFERENCES payers (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Guarded on the old column still being there: a half-applied file re-runs from the top.
SET @haspayerid := (SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'payerschedules'
                      AND COLUMN_NAME = 'payerid');
SET @sql := IF(@haspayerid > 0,
  'INSERT IGNORE INTO schedulepayers (scheduleid, payerid, accountid)
     SELECT recordid, payerid, accountid FROM payerschedules WHERE payerid IS NOT NULL',
  'DO 0');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := IF(@haspayerid > 0,
  'UPDATE payerschedules SET privatepay = 1 WHERE payerid IS NULL',
  'DO 0');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

ALTER TABLE payerschedules DROP FOREIGN KEY IF EXISTS fk_payerschedules_payer;
ALTER TABLE payerschedules DROP COLUMN IF EXISTS payerid;
