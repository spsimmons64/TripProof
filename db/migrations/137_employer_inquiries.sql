-- ################################################################################################
-- # 137 - asking previous employers, and proving you asked.
-- #
-- # 49 CFR 391.23(d) and (e) make the carrier ask every DOT-regulated employer from the previous
-- # three years about accidents and about drug and alcohol violations. What 391.23(i) then says is
-- # the part that decides how this is built:
-- #
-- #     the carrier must document a good faith effort to obtain the information, and the
-- #     previous employer's failure to respond does not relieve the carrier of the obligation
-- #
-- # So the thing being recorded is not "did the answer arrive". It is EVERY ATTEMPT: what was sent,
-- # to whom, by what means, on what date. An employer who never replies leaves a requirement that
-- # is satisfied by the record of asking, signed off as a good faith effort - and a file with one
-- # unanswered letter in it is a different file from one with three attempts across two channels.
-- #
-- #   inquiry  ----< attempt (email, fax, mail, phone, in person)
-- #      |
-- #      +-- answered   the employer replied, online or on paper
-- #      +-- effort     nobody replied, and the asking is the evidence
-- #
-- # The attempts are their own table because there is no limit to how many there are, and because
-- # collapsing them into "last tried on" throws away exactly what 391.23(i) asks to see.
-- #
-- # The reply itself is kept structured rather than as prose: an accident answer and a drug and
-- # alcohol answer are two different statutory questions with different consequences, and a single
-- # free-text box would make them one.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS employerinquiries (
    recordid        VARCHAR(36)  NOT NULL,
    accountid       VARCHAR(36)  NOT NULL,
    driverid        VARCHAR(36)  NOT NULL,

    -- Who is being asked. Copied from the application rather than read through it: the driver may
    -- correct their application later, and an inquiry already sent was sent to this address.
    employer        VARCHAR(160) NOT NULL,
    contactname     VARCHAR(120) NULL,
    email           VARCHAR(160) NULL,
    fax             VARCHAR(40)  NULL,
    phone           VARCHAR(40)  NULL,
    address1        VARCHAR(160) NULL,
    city            VARCHAR(80)  NULL,
    state           VARCHAR(2)   NULL,
    zip             VARCHAR(12)  NULL,

    employedfrom    DATE         NULL,
    employedthrough DATE         NULL,
    dotregulated    TINYINT(1)   NOT NULL DEFAULT 1,
    safetysensitive TINYINT(1)   NOT NULL DEFAULT 1,

    -- The link the employer answers on, where they have an email address.
    token           VARCHAR(64)  NOT NULL,
    expireson       DATETIME     NULL,

    -- The reply. 391.23(d) is the accident question; (e) is drug and alcohol. Two questions, two
    -- answers, because they are not the same question and do not have the same consequence.
    respondedon     DATETIME     NULL,
    respondedby     VARCHAR(120) NULL,          -- who at the employer answered
    respondedip     VARCHAR(45)  NULL,
    employed        TINYINT(1)   NULL,          -- did this person work for you at all
    accidents       JSON         NULL,          -- 391.23(d): the accident register entries
    drugalcohol     JSON         NULL,          -- 391.23(e): violations, refusals, return to duty
    responsenote    TEXT         NULL,
    documentid      VARCHAR(36)  NULL,          -- a reply that came back on paper

    -- 391.23(i). Signed off by the office when nobody answered, over the attempts below.
    effortclosedon  DATETIME     NULL,
    effortclosedby  VARCHAR(36)  NULL,
    effortnote      VARCHAR(512) NULL,

    createdon       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    createdby       VARCHAR(36)  NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_employerinquiries_token (token),
    KEY ix_employerinquiries_driver (accountid, driverid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Every attempt, in its own row. This is the good faith effort.
CREATE TABLE IF NOT EXISTS employerinquiryattempts (
    recordid    VARCHAR(36)  NOT NULL,
    inquiryid   VARCHAR(36)  NOT NULL,
    accountid   VARCHAR(36)  NOT NULL,
    channel     VARCHAR(12)  NOT NULL,         -- email | fax | mail | phone | inperson
    sentto      VARCHAR(255) NULL,             -- the address, number or person it went to
    senton      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    outcome     VARCHAR(16)  NULL,             -- sent | failed | noanswer | refused | answered
    note        VARCHAR(512) NULL,
    documentid  VARCHAR(36)  NULL,             -- the letter sent, or a fax receipt
    enteredby   VARCHAR(36)  NULL,
    PRIMARY KEY (recordid),
    KEY ix_employerattempts_inquiry (inquiryid, senton),
    CONSTRAINT fk_employerattempt_inquiry FOREIGN KEY (inquiryid)
        REFERENCES employerinquiries (recordid) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
