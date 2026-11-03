-- ################################################################################################
-- # 399 - the rules a broker's contract sets, kept on the company's own line for that broker and
-- # enforced only where filled in: an on-time window, a billing deadline, a trip number on every
-- # claim, caps on waiting and miles, notice to return a trip, and a signature on every leg.
-- ################################################################################################

ALTER TABLE accountpayers ADD COLUMN IF NOT EXISTS ontimeminutes SMALLINT NULL AFTER afterhourscontact;
ALTER TABLE accountpayers ADD COLUMN IF NOT EXISTS billdays SMALLINT NULL AFTER ontimeminutes;
ALTER TABLE accountpayers ADD COLUMN IF NOT EXISTS tripnumberrequired TINYINT(1) NOT NULL DEFAULT 0 AFTER billdays;
ALTER TABLE accountpayers ADD COLUMN IF NOT EXISTS waitcapminutes SMALLINT NULL AFTER tripnumberrequired;
ALTER TABLE accountpayers ADD COLUMN IF NOT EXISTS milecap DECIMAL(6,1) NULL AFTER waitcapminutes;
ALTER TABLE accountpayers ADD COLUMN IF NOT EXISTS returnnoticehours SMALLINT NULL AFTER milecap;
ALTER TABLE accountpayers ADD COLUMN IF NOT EXISTS signaturerequired TINYINT(1) NOT NULL DEFAULT 0 AFTER returnnoticehours;

-- The broker's own number for the trip, which its claims are matched on.
ALTER TABLE trips ADD COLUMN IF NOT EXISTS brokertripno VARCHAR(40) NULL AFTER brokerid;
