-- ################################################################################################
-- # 390 - a write-down: what is given up on an invoice, with why. Kept beside what was paid, never
-- # counted as money received.
-- ################################################################################################

ALTER TABLE billpayments ADD COLUMN IF NOT EXISTS writedown DECIMAL(12,2) NOT NULL DEFAULT 0 AFTER amount;
