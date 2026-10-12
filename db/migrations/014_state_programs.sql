-- ################################################################################################
-- # 014 - state regulatory research: each state's NEMT program profile, and where every rule came from.
-- #
-- # stateprograms   one row per state (plus 'US' for the federal layer), loaded from the research
-- #                 files db/sources/states/<ST>.json (see RESEARCH_SPEC.md): the Medicaid agency,
-- #                 delivery model, brokers, governing manual, State Plan and code citations, the full
-- #                 researched checklist (including items that can't be checked per trip), and the
-- #                 open questions. lastverifiedon/verifiedby record the human review.
-- # requirements    + the verbatim quote, the authority (federal/state/broker/plan) and the research
-- #                 confidence behind each rule.
-- # sources         + version, effective date and last-verified date of each document.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS stateprograms (
    state          CHAR(2)       NOT NULL,
    medicaidagency VARCHAR(255)  NULL,
    agencyurl      VARCHAR(512)  NULL,
    programname    VARCHAR(255)  NULL,
    deliverymodel  VARCHAR(20)   NULL,
    deliverydetail TEXT          NULL,
    brokers        LONGTEXT      NULL CHECK (brokers IS NULL OR JSON_VALID(brokers)),
    providermanual LONGTEXT      NULL CHECK (providermanual IS NULL OR JSON_VALID(providermanual)),
    stateplan      LONGTEXT      NULL CHECK (stateplan IS NULL OR JSON_VALID(stateplan)),
    admincode      LONGTEXT      NULL CHECK (admincode IS NULL OR JSON_VALID(admincode)),
    checklist      LONGTEXT      NULL CHECK (checklist IS NULL OR JSON_VALID(checklist)),
    openquestions  LONGTEXT      NULL CHECK (openquestions IS NULL OR JSON_VALID(openquestions)),
    researchfile   VARCHAR(255)  NULL,
    researchedon   DATE          NULL,
    loadedon       DATETIME      NULL,
    lastverifiedon DATE          NULL,
    verifiedby     VARCHAR(36)   NULL,
    added          DATETIME      NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated        DATETIME      NULL,
    PRIMARY KEY (state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE requirements
    ADD COLUMN IF NOT EXISTS quote      TEXT        NULL AFTER citation,
    ADD COLUMN IF NOT EXISTS authority  VARCHAR(12) NULL AFTER quote,
    ADD COLUMN IF NOT EXISTS confidence VARCHAR(8)  NULL AFTER authority,
    ADD COLUMN IF NOT EXISTS sourceurl  VARCHAR(512) NULL AFTER confidence;

ALTER TABLE sources
    ADD COLUMN IF NOT EXISTS version        VARCHAR(64) NULL AFTER publishedon,
    ADD COLUMN IF NOT EXISTS effectiveon    DATE        NULL AFTER version,
    ADD COLUMN IF NOT EXISTS lastverifiedon DATE        NULL AFTER accessedon;
