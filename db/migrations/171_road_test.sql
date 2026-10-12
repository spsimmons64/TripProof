-- ################################################################################################
-- # 171 - the road test, as one thing that ends in a certificate.
-- #
-- # 49 CFR 391.31 is one event with one output: an examiner takes the driver out in a vehicle
-- # representative of what they will drive, forms a view, and - if the driver can do it - signs a
-- # certificate. Keeping "the test" and "the certificate" as two unrelated documents to be uploaded
-- # separately loses the thing that matters, which is that the certificate is the RESULT of the
-- # test and means nothing without it.
-- #
-- # So one record: who was tested, in what, by whom, what the examiner saw item by item, and what
-- # they decided. A pass renders the certificate from that record; a fail leaves the driver not
-- # qualified and the evaluation still on file, which is exactly what an auditor wants to see.
-- #
-- # THE EXAMINER IS OUTSIDE THIS OFFICE
-- #
-- # Often they are: a contracted safety manager, somebody at another company, a trainer. So the
-- # test goes to them the way a safety performance inquiry goes to a previous employer - a link,
-- # answered by somebody with no login - and comes back needing a reading, because everything from
-- # outside does.
-- #
-- # The ratings are stored as JSON rather than as forty columns: they are a form's answers, the
-- # form will grow a question one day, and nothing in the engine reads an individual item. What the
-- # engine reads is `result`.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS roadtests (
    recordid        VARCHAR(36)  NOT NULL PRIMARY KEY,
    accountid       VARCHAR(36)  NOT NULL,
    driverid        VARCHAR(36)  NOT NULL,

    -- Who is taking it out, and how to reach them.
    examinername    VARCHAR(128) NULL,
    examinertitle   VARCHAR(128) NULL,
    examinerorg     VARCHAR(160) NULL,
    examineremail   VARCHAR(190) NULL,

    -- 391.31(b): a vehicle representative of the one the driver will operate.
    vehicleid       VARCHAR(36)  NULL,
    vehicledescr    VARCHAR(160) NULL,
    vehicletype     VARCHAR(24)  NULL,     -- car | cmv | bus | other
    vin             VARCHAR(32)  NULL,
    gvwr            INT          NULL,
    seats           INT          NULL,
    airbrakes       TINYINT(1)   NULL,
    manual          TINYINT(1)   NULL,
    trailer         TINYINT(1)   NULL,
    representative  TINYINT(1)   NULL,

    testedon        DATE         NULL,
    startedat       VARCHAR(8)   NULL,
    endedat         VARCHAR(8)   NULL,
    miles           INT          NULL,

    -- The examiner's view, item by item: {"pretrip": "s", "backing": "u", ...}
    ratings         LONGTEXT     NULL,
    extras          LONGTEXT     NULL,     -- the passenger/NEMT section, same shape
    comments        VARCHAR(2000) NULL,

    -- pass | fail. NULL until the examiner says.
    result          VARCHAR(8)   NULL,

    -- How it reaches the examiner, and what they signed.
    token           VARCHAR(64)  NOT NULL,
    sentto          VARCHAR(190) NULL,
    senton          DATETIME     NULL,
    expireson       DATETIME     NULL,
    completedon     DATETIME     NULL,
    certsignature   VARCHAR(160) NULL,
    certfontkey     VARCHAR(24)  NULL,
    completedip     VARCHAR(45)  NULL,

    -- The certificate, rendered on a pass, and the office's reading of what came back.
    documentid      VARCHAR(36)  NULL,
    reviewedon      DATETIME     NULL,
    reviewedby      VARCHAR(36)  NULL,

    createdby       VARCHAR(36)  NULL,
    createdon       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),

    UNIQUE KEY ux_roadtests_token (token),
    KEY ix_roadtests_driver (accountid, driverid, testedon),
    CONSTRAINT fk_roadtests_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
    CONSTRAINT fk_roadtests_driver FOREIGN KEY (driverid) REFERENCES drivers (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
