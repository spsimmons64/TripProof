-- ################################################################################################
-- # 131 - asking a driver for a document they hold.
-- #
-- # Some requirements can only be answered by paper the driver has and the company does not: the
-- # notice a state sent them when their licence was acted against, a certificate from a course they
-- # took before they arrived. Until now the only ways to get one were to stand over the driver or to
-- # wait for them to post it, and the requirement sat grey in the meantime with nothing recording
-- # that anybody had asked.
-- #
-- # An upload request is the signing request's twin, and deliberately so:
-- #
-- #   the office asks     -> a row, a random token, an email with the link
-- #   the driver opens it -> what is wanted and who wants it, and nothing else given away
-- #   the driver proves   -> date of birth and Social Security number, as in the application
-- #   the driver uploads  -> the file lands as a credential on their file, against the requirement
-- #
-- # The token alone uploads nothing: it says which document is wanted, not who is sitting at it.
-- # And the asking is itself a fact - a requirement nobody has chased reads differently from one
-- # where the driver was asked a fortnight ago and has not answered.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS uploadrequests (
    recordid     VARCHAR(36)  NOT NULL,
    accountid    VARCHAR(36)  NOT NULL,
    driverid     VARCHAR(36)  NOT NULL,

    -- The credential type being asked for. It is what the file becomes when it arrives, so the
    -- request and the record it produces cannot disagree about what was wanted.
    credentialcode VARCHAR(48) NOT NULL,

    token        VARCHAR(64)  NOT NULL,
    sentto       VARCHAR(160) NULL,
    senton       DATETIME     NULL,
    expireson    DATETIME     NOT NULL,
    uploadedon   DATETIME     NULL,
    documentid   VARCHAR(36)  NULL,
    credentialid VARCHAR(36)  NULL,
    cancelledon  DATETIME     NULL,
    requestedby  VARCHAR(36)  NULL,
    createdon    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_uploadrequests_token (token),
    KEY ix_uploadrequests_driver (accountid, driverid, credentialcode)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
