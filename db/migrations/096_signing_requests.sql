-- ################################################################################################
-- # 096 - asking a driver to sign something after their application is in.
-- #
-- # A file is not finished when the application is submitted. A policy is revised, a consent was
-- # never given, a form was signed on paper and lost. Until now the only way a driver could sign
-- # anything was the application itself, which closes when it is submitted - so the office's only
-- # options were to chase the driver in person or to hold a paper copy nobody can verify.
-- #
-- # A signing request is one document, for one driver, reachable by one link. It proves who is at
-- # the keyboard the same way the application does - date of birth and Social Security number - so
-- # a link that goes astray signs nothing.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS signingrequests (
    recordid    VARCHAR(36)  NOT NULL,
    accountid   VARCHAR(36)  NOT NULL,
    driverid    VARCHAR(36)  NOT NULL,
    doctype     VARCHAR(48)  NOT NULL,       -- what they are being asked to sign
    token       VARCHAR(64)  NOT NULL,       -- the link; random, and useless once signed
    sentto      VARCHAR(255) NULL,           -- where it was sent, as it was sent
    senton      DATETIME     NULL,
    expireson   DATETIME     NOT NULL,
    signedon    DATETIME     NULL,
    cancelledon DATETIME     NULL,
    requestedby VARCHAR(36)  NULL,
    createdon   DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_signingrequests_token (token),
    KEY ix_signingrequests_driver (accountid, driverid, doctype, signedon),
    CONSTRAINT fk_signingrequests_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_signingrequests_driver FOREIGN KEY (driverid) REFERENCES drivers (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
