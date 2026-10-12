-- ################################################################################################
-- # 005 - notification read state.
-- #
-- # Notifications themselves are not stored: they are computed from live data on each request
-- # (a credential about to lapse, a draft waiting for review), so they can never go stale. Each one
-- # carries a stable key, e.g. "expiring:<credentialid>" or "draft:<rulesetid>"; this table only
-- # remembers which keys a user has already read. A condition that clears and comes back later with
-- # a new key (a new draft, a new day's at-risk count) shows as unread again.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS notificationreads (
    userid   VARCHAR(36)  NOT NULL,
    notekey  VARCHAR(128) NOT NULL,
    readon   DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (userid, notekey),
    CONSTRAINT fk_notificationreads_user FOREIGN KEY (userid) REFERENCES users (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
