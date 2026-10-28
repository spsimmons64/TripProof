-- ################################################################################################
-- # 367 - "held up" on the way is over once the trip is done.
-- #
-- # The driver app now closes a traffic report when the leg is completed (routers/driverapp.py).
-- # Any left open on a leg already completed is closed the same way.
-- ################################################################################################

UPDATE tripissues i
JOIN triplegs l ON l.recordid = i.legid
SET i.resolvedon = UTC_TIMESTAMP(), i.resolutionkind = 'carriedon', i.resolution = 'THE TRIP WAS COMPLETED'
WHERE i.kind = 'traffic' AND i.resolvedon IS NULL AND l.executionstate = 'completed';
