-- ################################################################################################
-- # 354 - a dispute about a leg is a record of its own: who raised it, when and why, and who
-- # settled it, when, how and on what basis.
-- #
-- # "Disputed" was only a word on the leg, with the reason - if anybody typed one - left in the
-- # activity log. Nobody settling it could see why it had been disputed, and nothing said it ever
-- # had been settled. A leg has at most one open dispute; a settled one stays, as history.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS tripdisputes (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    tripid       VARCHAR(36)  NOT NULL,
    legid        VARCHAR(36)  NOT NULL,
    raisedon     DATETIME     NOT NULL,
    raisedby     VARCHAR(36)  NULL,
    reason       TEXT         NULL,
    settledon    DATETIME     NULL,
    settledby    VARCHAR(36)  NULL,
    settlement   VARCHAR(16)  NULL,       -- driven | noshow | aborted | cancelled
    settlenote   TEXT         NULL,
    PRIMARY KEY (recordid),
    KEY ix_tripdisputes_leg (accountid, legid, settledon)
);

-- The legs already disputed, from what was written when they were: the reason, if one was given,
-- is in the activity log entry that recorded it.
INSERT INTO tripdisputes (recordid, accountid, tripid, legid, raisedon, raisedby, reason)
SELECT UUID(), l.accountid, l.tripid, l.recordid,
       COALESCE((SELECT MAX(a.added) FROM activitylog a
                  WHERE a.accountid = l.accountid AND a.action = 'trip-outcome' AND a.entityid = l.tripid
                    AND JSON_UNQUOTE(JSON_EXTRACT(a.detail, '$.legid')) = l.recordid), UTC_TIMESTAMP()),
       (SELECT a.userid FROM activitylog a
         WHERE a.accountid = l.accountid AND a.action = 'trip-outcome' AND a.entityid = l.tripid
           AND JSON_UNQUOTE(JSON_EXTRACT(a.detail, '$.legid')) = l.recordid
         ORDER BY a.added DESC LIMIT 1),
       (SELECT NULLIF(JSON_UNQUOTE(JSON_EXTRACT(a.detail, '$.note')), 'null') FROM activitylog a
         WHERE a.accountid = l.accountid AND a.action = 'trip-outcome' AND a.entityid = l.tripid
           AND JSON_UNQUOTE(JSON_EXTRACT(a.detail, '$.legid')) = l.recordid
         ORDER BY a.added DESC LIMIT 1)
FROM triplegs l
WHERE l.outcomestate = 'disputed'
  AND NOT EXISTS (SELECT 1 FROM tripdisputes d WHERE d.legid = l.recordid AND d.settledon IS NULL);
