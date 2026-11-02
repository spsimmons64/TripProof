-- ################################################################################################
-- # 392 - a driving record read as disqualifying stops the driver on every trip until the office
-- # clears it, with why, against a newer clean record. The finding itself stays as it was read.
-- ################################################################################################

ALTER TABLE drivermvrs ADD COLUMN IF NOT EXISTS liftedon DATETIME NULL AFTER note;
ALTER TABLE drivermvrs ADD COLUMN IF NOT EXISTS liftedby VARCHAR(36) NULL AFTER liftedon;
ALTER TABLE drivermvrs ADD COLUMN IF NOT EXISTS liftreason VARCHAR(600) NULL AFTER liftedby;
