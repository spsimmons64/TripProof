-- ################################################################################################
-- # 011 - each user's own time zone, for showing timestamps (sign-ins, activity, invoices…).
-- #
-- # Display only. Business times - trip pickups, credential dates - stay in the operator's local
-- # wall clock (accounts.timezone) and are shown as recorded. NULL = use the account's time zone.
-- # TripProof staff start on Eastern.
-- ################################################################################################
ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) NULL AFTER role;

UPDATE users u JOIN accounts a ON a.recordid = u.accountid SET u.timezone = 'America/New_York'
WHERE a.platform = 1 AND u.timezone IS NULL;
