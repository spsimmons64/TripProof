-- ################################################################################################
-- # 389 - invoices reach the passenger: an email address, a billing contact, and a way to pay.
-- #
-- # The private code is what an emailed link or a printed QR code carries, so a passenger reaches
-- # their own invoice with no login. Money goes to the company's own merchant account; card details
-- # never reach TripProof. A processor reference on a payment means one that is told twice counts once.
-- ################################################################################################

ALTER TABLE passengers ADD COLUMN IF NOT EXISTS email VARCHAR(255) NULL AFTER phone;
ALTER TABLE passengers ADD COLUMN IF NOT EXISTS billingname VARCHAR(160) NULL AFTER email;
ALTER TABLE passengers ADD COLUMN IF NOT EXISTS billingemail VARCHAR(255) NULL AFTER billingname;
ALTER TABLE passengers ADD COLUMN IF NOT EXISTS billingaddress VARCHAR(255) NULL AFTER billingemail;

ALTER TABLE tripinvoices ADD COLUMN IF NOT EXISTS paytoken VARCHAR(64) NULL AFTER number;
ALTER TABLE tripinvoices ADD COLUMN IF NOT EXISTS billtoemail VARCHAR(255) NULL AFTER billtophone;
ALTER TABLE tripinvoices ADD COLUMN IF NOT EXISTS emailedon DATETIME NULL AFTER billtoemail;
ALTER TABLE tripinvoices ADD COLUMN IF NOT EXISTS emailerror VARCHAR(255) NULL AFTER emailedon;
UPDATE tripinvoices SET paytoken = REPLACE(UUID(), '-', '') WHERE paytoken IS NULL;
ALTER TABLE tripinvoices ADD UNIQUE KEY IF NOT EXISTS ux_tripinvoices_token (paytoken);

ALTER TABLE billpayments ADD COLUMN IF NOT EXISTS processorref VARCHAR(255) NULL AFTER note;
ALTER TABLE billpayments ADD UNIQUE KEY IF NOT EXISTS ux_billpayments_ref (accountid, processorref);
