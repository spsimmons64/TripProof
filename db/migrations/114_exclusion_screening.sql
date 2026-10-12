-- ################################################################################################
-- # 114 - monthly exclusion screening: the run, and the record of every driver in it.
-- #
-- # An excluded driver is the one compliance failure that costs money backwards: every trip they
-- # carried becomes an overpayment. OIG republishes the list monthly, by the 10th, so a check from
-- # eight weeks ago can be wrong without anybody doing anything - the driver did not change, the
-- # list did. That is why this is a scheduled job and not a button.
-- #
-- # TWO TABLES, AND THE FIRST ONE IS THE POINT.
-- #
-- #   exclusionruns    one download of one list. It pins WHICH list was screened against - the
-- #                    file's last-modified stamp, its size, its sha256. "We checked in September"
-- #                    is an assertion; "we checked against the file OIG published on 2026-09-10,
-- #                    sha256 abc..." is evidence.
-- #   exclusionchecks  one driver, one source, one run, one result - INCLUDING the clean ones. The
-- #                    commonest audit failure is keeping only the hits. The record that the check
-- #                    ran and came back clear is the thing being audited.
-- #
-- # WHAT THE MACHINE CANNOT FINISH. The downloadable LEIE carries no SSN and no EIN - the Privacy
-- # Act forbids it - so a name match is a CANDIDATE and never a confirmation. OIG is explicit: "It
-- # is not sufficient to simply find a matching first and last name on the LEIE." Confirmation
-- # happens on their online form, against the SSN, by a person, and the evidence is a screenshot.
-- # So a hit lands in `potential` and waits for somebody; nothing here ever writes `confirmed` on
-- # its own.
-- #
-- # AND LIABILITY DOES NOT TRANSFER. OIG's 2013 Special Advisory Bulletin: "because it is the
-- # provider's responsibility to determine whether employees are excluded, the providers will
-- # retain the potential CMP liability if they employ or contract with an excluded person." So
-- # `performedby` records who actually ran it - us, a vendor, or a contractor who screened their
-- # own people - and a contractor's attestation can be attached rather than assumed.
-- ################################################################################################

-- One download of one list, pinned so the answer can be reproduced.
CREATE TABLE IF NOT EXISTS exclusionruns (
    recordid     VARCHAR(36)  NOT NULL,
    source       VARCHAR(24)  NOT NULL,      -- OIG_LEIE | SAM_EXCLUSIONS | FL_AHCA
    -- What was actually screened against. The stamp the publisher put on it, not the day we ran.
    datasetstamp VARCHAR(64)  NULL,          -- e.g. the file's Last-Modified header
    datasetbytes BIGINT       NULL,
    datasetsha   CHAR(64)     NULL,
    records      INT          NULL,          -- rows in the list, as a sanity check on a short file
    startedon    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finishedon   DATETIME     NULL,
    state        VARCHAR(12)  NOT NULL DEFAULT 'running',   -- running | done | failed
    note         VARCHAR(512) NULL,
    PRIMARY KEY (recordid),
    KEY ix_exclusionruns_source (source, startedon)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One driver, one source, one run. Clean results are kept: they are the evidence.
CREATE TABLE IF NOT EXISTS exclusionchecks (
    recordid      VARCHAR(36)  NOT NULL,
    accountid     VARCHAR(36)  NOT NULL,
    driverid      VARCHAR(36)  NOT NULL,
    runid         VARCHAR(36)  NULL,         -- NULL when somebody filed a check by hand
    source        VARCHAR(24)  NOT NULL,
    checkedon     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Every name actually submitted. OIG holds only the name known at exclusion, so maiden and
    -- former names have to be searched separately and the search has to say which it tried.
    namessearched VARCHAR(512) NOT NULL,
    dobsearched   DATE         NULL,

    result        VARCHAR(16)  NOT NULL,     -- clear | potential | confirmed | error
    candidates    JSON         NULL,         -- the matching rows, verbatim from the source
    -- How a potential match was settled, by a person, on the online form.
    verifiedby    VARCHAR(36)  NULL,
    verifiedon    DATETIME     NULL,
    verifymethod  VARCHAR(24)  NULL,         -- ssn | ein | npi | dob_ruled_out
    evidencedocid VARCHAR(36)  NULL,         -- the screenshot OIG asks to be retained
    note          VARCHAR(512) NULL,

    -- Who ran it. Outsourcing the screening does not outsource the liability, so this is recorded
    -- rather than assumed to be us.
    performedby   VARCHAR(32)  NOT NULL DEFAULT 'tripproof',   -- tripproof | vendor:<name> | contractor
    PRIMARY KEY (recordid),
    KEY ix_exclusionchecks_driver (driverid, source, checkedon),
    KEY ix_exclusionchecks_open (accountid, result, checkedon),
    KEY ix_exclusionchecks_run (runid),
    CONSTRAINT fk_exclusionchecks_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The requirement stops being answered by a hand-filed credential and starts being answered by the
-- screening itself. Monthly, because that is the cadence OIG publishes at and the cadence its 2013
-- bulletin recommends: "OIG updates the LEIE monthly, so screening employees and contractors each
-- month best minimizes potential overpayment and CMP liability."
UPDATE compliancerules
   SET evidencesource = 'exclusioncheck:OIG_LEIE', evidencekind = 'query', recurrencedays = 31
 WHERE code = 'EXCLUSION_CHECK_DRIVER' AND effectiveto IS NULL;
