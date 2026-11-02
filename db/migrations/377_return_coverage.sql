-- ################################################################################################
-- # 377 - the end-of-day handoff: a will-call still out near closing is covered, on the record.
-- #
-- # From ninety minutes before closing, every will-call return the company is still responsible
-- # for, and nobody has collected, has to have its coverage recorded: who is on call for it, how they
-- # are reached and until when - or the other provider that has taken it. Pressing Acknowledge is
-- # not coverage; this row is. Until it exists the return stays under Needs Attention.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS returncoverage (
    recordid      VARCHAR(36)  NOT NULL,
    accountid     VARCHAR(36)  NOT NULL,
    legid         VARCHAR(36)  NOT NULL,
    kind          VARCHAR(8)   NOT NULL,            -- oncall | other
    person        VARCHAR(160) NOT NULL,            -- the on-call person, or the other provider
    contact       VARCHAR(160) NULL,                -- how they are reached, or the provider's confirmation
    until         DATETIME     NULL,                -- the end of the cover, company clock
    recordedon    DATETIME     NOT NULL,
    recordedby    VARCHAR(36)  NOT NULL,
    PRIMARY KEY (recordid),
    KEY ix_returncoverage_leg (accountid, legid, recordedon)
);
