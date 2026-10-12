-- ################################################################################################
-- # 097 - a record of things having changed.
-- #
-- # Every screen in the portal reads what is true now and has no way of learning that it stopped
-- # being true a moment ago. Today that means a stale page until somebody presses reload; tomorrow
-- # it means a map that does not move.
-- #
-- # An event says only that something changed, and which thing: an account, a subject, an id. It
-- # carries no content - a client that hears "this driver changed" asks the endpoints it already
-- # calls, which already decide what that user may see. So the feed can never leak what a screen
-- # would not have shown anyway, and it never becomes a second copy of the truth to keep in step.
-- #
-- # `seq` is the cursor: a client remembers the last one it saw and asks for what came after. Two
-- # transactions can take sequence numbers in one order and commit in the other, so a reader that
-- # only ever moves forward can in principle step over one. That is why an event is a nudge to go
-- # and look rather than the thing itself - the look is what is authoritative.
-- #
-- # This is the outbox the live transports will be built on: polling today, server-sent events when
-- # the office wants it instant, and a socket if a dispatch console ever needs to talk back.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS events (
    seq       BIGINT       NOT NULL AUTO_INCREMENT,
    recordid  VARCHAR(36)  NOT NULL,
    accountid VARCHAR(36)  NOT NULL,
    subject   VARCHAR(24)  NOT NULL,      -- driver | vehicle | trip | company
    subjectid VARCHAR(36)  NULL,
    kind      VARCHAR(48)  NOT NULL,      -- what happened, in the fewest words that distinguish it
    detail    VARCHAR(255) NULL,          -- ids and codes only, never content
    createdon DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (seq),
    UNIQUE KEY ux_events_record (recordid),
    KEY ix_events_account (accountid, seq),
    CONSTRAINT fk_events_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
