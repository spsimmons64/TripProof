-- ################################################################################################
-- # 393 - a late cancellation is priced by the fee schedule like a no-show: how many hours before
-- # the pickup a cancellation counts as late belongs to the rate, because each contract sets its own.
-- ################################################################################################

ALTER TABLE payerrates ADD COLUMN IF NOT EXISTS cancelwithinhours DECIMAL(6,2) NULL AFTER minimumunits;
