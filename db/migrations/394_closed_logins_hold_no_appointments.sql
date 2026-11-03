-- ################################################################################################
-- # 394 - somebody whose login is closed no longer holds a company appointment. The rows stay, with
-- # the day it ended, because who held a role and when is what an audit asks.
-- ################################################################################################

UPDATE companyroles r JOIN users u ON u.recordid = r.userid
   SET r.until = DATE(u.deleted)
 WHERE r.until IS NULL AND u.deleted IS NOT NULL;
