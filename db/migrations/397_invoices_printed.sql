-- ################################################################################################
-- # 397 - an invoice with no email address has to go by post. When it was printed, and by whom,
-- # so the To Print list holds only those still waiting.
-- ################################################################################################

ALTER TABLE tripinvoices ADD COLUMN IF NOT EXISTS printedon DATETIME NULL AFTER lastremindedon;
ALTER TABLE tripinvoices ADD COLUMN IF NOT EXISTS printedby VARCHAR(36) NULL AFTER printedon;
