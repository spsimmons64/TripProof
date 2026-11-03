-- ################################################################################################
-- # 401 - a leg driven through the app with the phone reporting where it was is a leg with GPS. Only
-- # imported trips used to be marked so; the legs already driven are put right here.
-- ################################################################################################

UPDATE triplegs l
   SET l.gps = 1
 WHERE l.gps = 0 AND l.executionstate = 'completed' AND l.driverid IS NOT NULL
   AND EXISTS (SELECT 1 FROM driverlocations p
                WHERE p.accountid = l.accountid AND p.driverid = l.driverid
                  AND p.recordedon BETWEEN (SELECT MIN(e.happenedon) FROM tripevents e WHERE e.legid = l.recordid AND e.state IN ('enroute', 'onboard'))
                                       AND (SELECT MAX(e.happenedon) FROM tripevents e WHERE e.legid = l.recordid AND e.state = 'completed'));
