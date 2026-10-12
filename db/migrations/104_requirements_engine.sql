-- ################################################################################################
-- # 104 - the requirements engine: three tables.
-- #
-- # The catalog that 103 removed said "this document type is required for this kind of driver". It
-- # could not say anything else, and almost everything that decides whether a rule reaches a driver
-- # is something else: the vehicle's weight and seating, whether passengers are carried for
-- # compensation, whether the run crosses a state line, who is paying, what the contract says.
-- #
-- # These three tables split apart what that one table ran together:
-- #
-- #   compliancerules      a rule. What it is, who says so, when it reaches somebody, what answers
-- #                        it, how often it comes round. Versioned - never edited in place.
-- #   complianceevidence   the record that answers a rule. It POINTS at a record that already
-- #                        exists - an MVR, a review, a test, a credential - and never copies it.
-- #                        One record can answer several rules, which is the whole point.
-- #   compliancestate      what the engine worked out. Derived, rewritten, never typed into.
-- #
-- # They are named `compliance*` rather than `requirement*` because `requirements` is already taken:
-- # it is the trip rules engine's table, the one rulesets and legchecks hang off. Two different
-- # things called a requirement in one schema is how the next confusion starts.
-- #
-- # Nothing reads these yet. They are created empty, and the engine that fills them is written
-- # against them rather than the other way round.
-- ################################################################################################


-- ------------------------------------------------------------------------------------------------
-- A rule.
--
-- `applieswhen` is the whole of the applicability logic, as an expression evaluated against facts
-- assembled at decision time - the vehicle, the driver, the operation, the payer. NULL means the
-- rule always applies. A new rule is a row; it is never a new column. For example, Part 391 in
-- interstate commerce:
--
--   {"all": [{"fact": "vehicle.cmv_federal", "is": true},
--            {"fact": "operation.interstate", "is": true}]}
--
-- and the Florida carve-out that drops Part 391 while keeping Part 382 (F.S. 316.302(2)(f)):
--
--   {"all": [{"fact": "operation.interstate", "is": false},
--            {"fact": "vehicle.cmv_florida", "is": true},
--            {"fact": "vehicle.gvwr", "lt": 26001}]}
--
-- Facts that are conclusions - cmv_federal, cmv_florida, cdl_required - are computed from what was
-- measured and recorded, never set by hand. A person who can tick "this is a commercial motor
-- vehicle" will eventually tick it wrong, and the engine would believe them.
-- ------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliancerules (
    recordid       VARCHAR(36)  NOT NULL,
    code           VARCHAR(48)  NOT NULL,      -- stable across versions: MVR_ANNUAL, EXCLUSION_CHECK
    name           VARCHAR(160) NOT NULL,
    subject        VARCHAR(8)   NOT NULL,      -- company | driver | vehicle

    -- Who says so. One authority type, never several - a rule is statutory or contractual, not both.
    authoritytype  VARCHAR(16)  NOT NULL,      -- statute | regulation | program | contract | policy
    authority      VARCHAR(96)  NULL,          -- FMCSA, AHCA, FDOT, CTD, a named broker
    jurisdiction   VARCHAR(8)   NOT NULL DEFAULT 'US',
    citation       VARCHAR(160) NULL,
    sourceurl      VARCHAR(512) NULL,

    -- When it reaches somebody.
    applieswhen    JSON         NULL,          -- NULL = always
    program        VARCHAR(48)  NULL,          -- NULL = every programme this company runs

    -- What answers it. A requirement is not a document: `evidencekind` says what would satisfy it,
    -- and `none` is a real answer - it is how a state rule that removes a federal one is written.
    evidencekind   VARCHAR(16)  NOT NULL,      -- document | query | test | process | attestation | none
    reviewrequired TINYINT(1)   NOT NULL DEFAULT 0,   -- a person must read the evidence
    determination  TINYINT(1)   NOT NULL DEFAULT 0,   -- it ends in qualified / disqualified
    blocking       TINYINT(1)   NOT NULL DEFAULT 1,   -- failing it stops the driver

    -- When it falls due, and when it comes round again.
    duestage       VARCHAR(12)  NULL,          -- prehire | predrive | athire | ongoing
    recurrence     VARCHAR(12)  NULL,          -- once | perhire | days | ondocument | event
    recurrencedays INT          NULL,
    warndays       INT          NOT NULL DEFAULT 30,

    -- How the answer is handled once it exists. 49 CFR 40.321 forbids releasing a DOT test result
    -- without the driver's own written consent, and 391.53 wants the safety performance history in
    -- a file with controlled access - so this is a property of the rule, inherited by its evidence,
    -- rather than something bolted on afterwards.
    sensitivity    VARCHAR(12)  NOT NULL DEFAULT 'normal',   -- normal | restricted
    retentionrule  VARCHAR(80)  NULL,          -- e.g. '5 years - 49 CFR 382.401(b)'

    -- Versioning. A rule is superseded, never edited: a trip decided in 2025 has to stay readable
    -- against the rule that was in force when it ran.
    effectivefrom  DATE         NOT NULL,
    effectiveto    DATE         NULL,          -- NULL = in force
    supersedes     VARCHAR(36)  NULL,          -- the rule this one stands in place of

    note           VARCHAR(512) NULL,
    sortorder      INT          NOT NULL DEFAULT 0,
    added          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    addedby        VARCHAR(36)  NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_req_version (code, jurisdiction, effectivefrom),
    KEY ix_req_inforce (subject, effectiveto),
    KEY ix_req_supersedes (supersedes)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ------------------------------------------------------------------------------------------------
-- What answers a rule.
--
-- This is the table that ends the bug we kept hitting. A row here says "that record, over there,
-- answers this requirement". It holds no copy of the record's state - no second `state` column to
-- drift out of step with the MVR, no second `outcome` beside the report's own. The dates and the
-- determination are here only because they are what the engine sorts and expires on, and they are
-- written from the source record whenever it changes.
--
-- The unique key allows one source record against many requirements, which is the point: a medical
-- certificate answers 49 CFR 391.45, F.A.C. 14-90.0041 and a broker's contract at once, and it is
-- filed once.
-- ------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS complianceevidence (
    recordid      VARCHAR(36)  NOT NULL,
    accountid     VARCHAR(36)  NOT NULL,
    ruleid        VARCHAR(36)  NOT NULL,
    subject       VARCHAR(8)   NOT NULL,       -- company | driver | vehicle
    subjectid     VARCHAR(36)  NOT NULL,

    -- The record that already holds this fact. Never a copy of it.
    sourcetable   VARCHAR(32)  NOT NULL,       -- drivermvrs | annualreviews | driverreports | ...
    sourceid      VARCHAR(36)  NOT NULL,

    effectiveon   DATE         NULL,           -- the date the record itself carries
    expireson     DATE         NULL,           -- NULL = it does not expire on its own
    determination VARCHAR(16)  NULL,           -- qualified | disqualified | clear | flagged |
                                               -- negative | positive | refusal | prohibited
    reviewedon    DATETIME     NULL,
    reviewedby    VARCHAR(36)  NULL,
    note          VARCHAR(512) NULL,
    added         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_evidence (ruleid, subject, subjectid, sourcetable, sourceid),
    KEY ix_evidence_subject (accountid, subject, subjectid),
    KEY ix_evidence_source (sourcetable, sourceid),
    CONSTRAINT fk_evidence_rule FOREIGN KEY (ruleid) REFERENCES compliancerules (recordid),
    CONSTRAINT fk_evidence_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ------------------------------------------------------------------------------------------------
-- What the engine worked out.
--
-- Derived, and only ever written by the engine. Nothing in the application sets a status here: if a
-- status is wrong the rule or the evidence is wrong, and that is where it gets fixed. Keeping this
-- rule is the difference between a system that can explain an answer and one that can only assert
-- it - which is why `why` is a sentence rather than a code.
--
-- `program` is '' for the general answer and a programme name for a programme-specific one, because
-- the same driver can be qualified for private pay and not for a broker at the same moment.
--
-- A prohibition is deliberately NOT a status here. A Clearinghouse bar, a positive test or an OIG
-- exclusion overrides the whole set rather than failing one member of it, so it stays in
-- driverprohibitions and is consulted before this table is even assembled.
-- ------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliancestate (
    recordid      VARCHAR(36)  NOT NULL,
    accountid     VARCHAR(36)  NOT NULL,
    subject       VARCHAR(8)   NOT NULL,
    subjectid     VARCHAR(36)  NOT NULL,
    ruleid        VARCHAR(36)  NOT NULL,
    program       VARCHAR(48)  NOT NULL DEFAULT '',   -- '' = the general answer

    -- notapplicable | pending | review | satisfied | expiring | expired | failed | waived
    status        VARCHAR(16)  NOT NULL,
    evidenceid    VARCHAR(36)  NULL,           -- what it is satisfied by, when it is
    since         DATE         NULL,
    until         DATE         NULL,           -- when this answer stops being true
    why           VARCHAR(255) NULL,           -- in words, for the person reading it
    computedon    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_state (subject, subjectid, ruleid, program),
    KEY ix_state_account (accountid, subject, status),
    KEY ix_state_due (accountid, until),
    CONSTRAINT fk_state_rule FOREIGN KEY (ruleid) REFERENCES compliancerules (recordid),
    CONSTRAINT fk_state_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
