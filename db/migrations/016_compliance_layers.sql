-- ################################################################################################
-- # 016 - compliance layers: what a transportation company must meet because of WHERE it operates,
-- # separate from what a payer (Medicaid, a broker) demands.
-- #
-- #   level     federal  (state 'US')      - applies everywhere
-- #             state                      - the account's state
-- #             county / city              - the account's county or city (county/city columns)
-- #             program                    - a payer layer: program 'MEDICAID' baseline per state,
-- #                                          and broker sets (brokerid) on top of it
-- #   Everything built so far (state baselines from the Medicaid guide/research, broker sets) is the
-- #   MEDICAID program layer.
-- #
-- # Requirements gain a category (driver, vehicle, company, insurance, licensing, employment), when
-- # they apply (applieswhen), and a new kind 'obligation': a legal duty shown on the
-- # compliance checklist but not checked trip by trip (wage law, I-9, registration …).
-- # Accounts gain a county so local rules can apply.
-- ################################################################################################
ALTER TABLE rulesets
    ADD COLUMN IF NOT EXISTS level   VARCHAR(8)  NOT NULL DEFAULT 'program' AFTER state,
    ADD COLUMN IF NOT EXISTS program VARCHAR(16) NULL AFTER level,
    ADD COLUMN IF NOT EXISTS county  VARCHAR(64) NULL AFTER program,
    ADD COLUMN IF NOT EXISTS city    VARCHAR(64) NULL AFTER county;

UPDATE rulesets SET level = 'program', program = 'MEDICAID' WHERE program IS NULL;

ALTER TABLE rulesets
    ADD CONSTRAINT IF NOT EXISTS ck_rulesets_level CHECK (level IN ('federal', 'state', 'county', 'city', 'program'));

ALTER TABLE requirements
    ADD COLUMN IF NOT EXISTS category  VARCHAR(12) NULL AFTER subject,
    ADD COLUMN IF NOT EXISTS applieswhen TEXT      NULL AFTER category;

ALTER TABLE requirements DROP CONSTRAINT IF EXISTS ck_requirements_kind;
ALTER TABLE requirements
    ADD CONSTRAINT IF NOT EXISTS ck_requirements_kind
        CHECK (kind IN ('credential','vehiclemileage','vehicleage','driverage','licenseyears','tripevidence','obligation'));

ALTER TABLE accounts ADD COLUMN IF NOT EXISTS county VARCHAR(64) NULL AFTER city;

-- Law research profile per jurisdiction ('US' or a state): the agencies that regulate a
-- transportation company there, known county/city regimes, what the research couldn't confirm, and
-- the human review. Loaded from db/sources/law/<J>.json (see that folder's RESEARCH_SPEC.md).
CREATE TABLE IF NOT EXISTS lawprofiles (
    jurisdiction   CHAR(2)      NOT NULL,
    agencies       LONGTEXT     NULL CHECK (agencies IS NULL OR JSON_VALID(agencies)),
    localregimes   LONGTEXT     NULL CHECK (localregimes IS NULL OR JSON_VALID(localregimes)),
    openquestions  LONGTEXT     NULL CHECK (openquestions IS NULL OR JSON_VALID(openquestions)),
    researchfile   VARCHAR(255) NULL,
    researchedon   DATE         NULL,
    loadedon       DATETIME     NULL,
    lastverifiedon DATE         NULL,
    verifiedby     VARCHAR(36)  NULL,
    added          DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated        DATETIME     NULL,
    PRIMARY KEY (jurisdiction)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
