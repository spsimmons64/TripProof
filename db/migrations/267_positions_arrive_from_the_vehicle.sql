-- Positions arrive from the vehicle.
--
-- A tracker in a van cannot sign in: there is no person at the wheel of the HTTP request, and
-- a session token minted for a dispatcher has no business living in a device that gets sold
-- with the vehicle. So the feed authenticates with a token of its own, held against the
-- account, presented on every post and rotatable without touching anybody's login.
--
-- It is a shared secret for ONE account. It can write positions and nothing else - it cannot
-- read a driver's file, order a check or see a test result - so the worst a leaked one does is
-- let somebody write false positions, which is bad but bounded, and is why it is rotatable.

ALTER TABLE accounts
  ADD COLUMN IF NOT EXISTS gpstoken VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS gpstokenon DATETIME NULL;

-- Which vehicle reported it. The driver is who was responsible; the vehicle is what the box is
-- bolted to, and an accident enquiry asks about the vehicle.
ALTER TABLE driverlocations
  ADD COLUMN IF NOT EXISTS vehicleid VARCHAR(36) NULL;
