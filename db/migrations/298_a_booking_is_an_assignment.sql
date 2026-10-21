-- The assignment history that booking a trip never wrote.
--
-- `tripassignments` was added in 290 as the record behind `triplegs.driverid`, with the intention
-- that the endpoint setting the column also wrote the row "so the two cannot drift". Booking did
-- not: a trip created straight onto a driver set the column and wrote no history. The effect was
-- quiet and bad. The leg's own timeline opened with a driver already on it as though nobody had
-- decided it; "Someone Is Out" ended assignments that did not exist; and a product whose claim is
-- that it can prove who was qualified to drive a given trip had no record of the first - usually
-- the only - time anybody was put on it.
--
-- Fixed in the booking endpoint. This puts back what is missing for trips already on file, using
-- the leg's own `added` as the honest date: it is when the assignment was made, because it was
-- made in the same breath as the leg.
INSERT INTO tripassignments (recordid, accountid, legid, driverid, vehicleid, assignedon,
                             assignedby, endreason)
SELECT UUID(), l.accountid, l.recordid, l.driverid, l.vehicleid, l.added, NULL, NULL
  FROM triplegs l
  JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
 WHERE (l.driverid IS NOT NULL OR l.vehicleid IS NOT NULL)
   AND NOT EXISTS (SELECT 1 FROM tripassignments a WHERE a.legid = l.recordid);
