-- ################################################################################################
-- # 385 - when a facility closes; and what the dispatch model no longer uses.
-- #
-- # A clinic can lock up with a will-call passenger still outside, whatever the company's own hours
-- # are, so a location can say when it closes. Booking order replaced the payer's dispatch priority,
-- # and every vehicle assignment has its driver now.
-- ################################################################################################

ALTER TABLE places ADD COLUMN IF NOT EXISTS closesat TIME NULL AFTER critical;
ALTER TABLE accountpayers DROP COLUMN IF EXISTS priority;
DELETE FROM dayshifts WHERE driverid IS NULL;
ALTER TABLE dayshifts MODIFY driverid VARCHAR(36) NOT NULL;
