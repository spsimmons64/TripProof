-- ################################################################################################
-- # 371 - a driver who goes out leaves their vehicle for somebody else.
-- #
-- # Driver Out ends the driver's vehicle assignment when they go, so the vehicle can be given to
-- # whoever is called in to cover; back at a time, they have it again from then. The absence keeps
-- # which vehicle it was and when that assignment would have ended, so Driver Is Back can hand it
-- # back to them - if nobody has been put in it meanwhile.
-- ################################################################################################

ALTER TABLE driverunavailable ADD COLUMN IF NOT EXISTS vehicleid VARCHAR(36) NULL AFTER note;
ALTER TABLE driverunavailable ADD COLUMN IF NOT EXISTS vehicleuntil DATETIME NULL AFTER vehicleid;
