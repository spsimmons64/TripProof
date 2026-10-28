-- ################################################################################################
-- # 362 - a will-call is not scheduled until the passenger calls.
-- #
-- # No pickup time, so no driver: Passenger Called gives the leg its time, and then it is assigned
-- # like any other (routers/trips.assign_leg now refuses one sooner). Any will-call that was given
-- # a driver before this rule has that assignment ended - kept on file, as every ended one is.
-- ################################################################################################

UPDATE tripassignments a
JOIN triplegs l ON l.recordid = a.legid
SET a.endedon = UTC_TIMESTAMP(), a.endreason = 'willcall'
WHERE l.pickupat IS NULL AND l.outcomestate IS NULL AND a.endedon IS NULL;

UPDATE triplegs SET driverid = NULL, vehicleid = NULL
WHERE pickupat IS NULL AND outcomestate IS NULL AND (driverid IS NOT NULL OR vehicleid IS NOT NULL);
