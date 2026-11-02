-- ################################################################################################
-- # 391 - putting billing right: a payment undone stays on file with why; a refund is its own
-- # record; miles the office corrects sit beside the GPS and driver figures, never over them; and
-- # an unpaid invoice remembers how many reminders it has had.
-- ################################################################################################

ALTER TABLE billpayments ADD COLUMN IF NOT EXISTS refund TINYINT(1) NOT NULL DEFAULT 0 AFTER denied;
ALTER TABLE billpayments ADD COLUMN IF NOT EXISTS voidedon DATETIME NULL AFTER recordedby;
ALTER TABLE billpayments ADD COLUMN IF NOT EXISTS voidedby VARCHAR(36) NULL AFTER voidedon;
ALTER TABLE billpayments ADD COLUMN IF NOT EXISTS voidreason VARCHAR(600) NULL AFTER voidedby;

ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS officemiles DECIMAL(8,2) NULL AFTER miles;
ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS officemilesreason VARCHAR(600) NULL AFTER officemiles;
ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS officemilesby VARCHAR(36) NULL AFTER officemilesreason;
ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS officemileson DATETIME NULL AFTER officemilesby;

ALTER TABLE tripinvoices ADD COLUMN IF NOT EXISTS remindercount INT NOT NULL DEFAULT 0 AFTER emailerror;
ALTER TABLE tripinvoices ADD COLUMN IF NOT EXISTS lastremindedon DATETIME NULL AFTER remindercount;
