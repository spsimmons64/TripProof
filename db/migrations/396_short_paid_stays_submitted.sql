-- ################################################################################################
-- # 396 - a trip is Paid only once nothing is owed on it. One paid short goes back to Submitted,
-- # where it stays until the rest is paid or written down.
-- ################################################################################################

UPDATE trips t
   SET t.billingstatus = 'billed'
 WHERE t.billingstatus = 'paid'
   AND t.billedamount - (SELECT COALESCE(SUM(p.amount + p.writedown), 0) FROM billpayments p
                          WHERE p.tripid = t.recordid AND p.denied = 0 AND p.voidedon IS NULL) > 0.004;
