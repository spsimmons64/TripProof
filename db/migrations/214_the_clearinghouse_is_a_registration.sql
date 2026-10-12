-- ################################################################################################
-- # 214 - the Clearinghouse registration is a registration, not a document.
-- #
-- # 202 made it `credential:CLEARINGHOUSE_REGISTRATION` - something the company uploads - and there
-- # is no such thing to upload. Registration is performed electronically at FMCSA; no form is
-- # completed, signed and filed. So the requirement asked for a document that does not exist and
-- # reported "Nothing on file yet", which is not the question. The question is whether the employer
-- # account exists and somebody here has verified it.
-- #
-- # What is actually worth holding is the state of that account: whether it is registered, when
-- # somebody last confirmed it, whether a consortium or third party administrator acts on the
-- # company's behalf and who, and whether a query plan has been bought - because queries cannot be
-- # run without one, and a registration with no plan is a registration that cannot do its job.
-- #
-- # NO EXPIRY, and deliberately no invented re-verification period. FMCSA sets none. The record
-- # carries the day it was last verified so staleness is visible; it does not turn a requirement
-- # red on a date nobody asked for.
-- #
-- # The authority line becomes Subpart G. 382.701 and 382.705 are two sections of it, and quoting
-- # only those two describes the queries and the reporting while leaving out the registration they
-- # both depend on.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS clearinghouseregistration (
    accountid      VARCHAR(36)  NOT NULL,
    registered     TINYINT(1)   NULL,          -- three-valued: nobody has said is not "no"
    verifiedon     DATE         NULL,          -- the day the account was established or confirmed
    lastverifiedon DATE         NULL,          -- the day somebody here last looked
    ctpaused       TINYINT(1)   NULL,
    ctpaname       VARCHAR(160) NULL,
    queryplan      TINYINT(1)   NULL,          -- queries cannot be run without one
    documentid     VARCHAR(36)  NULL,          -- the account confirmation, where there is one
    note           VARCHAR(512) NULL,
    updatedby      VARCHAR(36)  NULL,
    updated        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (accountid),
    CONSTRAINT fk_chregistration_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

UPDATE compliancerules
   SET name           = 'FMCSA Drug and Alcohol Clearinghouse employer registration',
       citation       = '49 CFR Part 382, Subpart G',
       evidencekind   = 'registration',
       evidencesource = 'clearinghouse',
       duestage       = 'ongoing',
       duetext        = 'Before employing or using a driver subject to Part 382',
       description    = 'Required when the company employs or uses drivers subject to 49 CFR Part '
                        '382 - those operating a commercial motor vehicle requiring a CDL or CLP. '
                        'Registration is performed electronically at FMCSA; there is no form to '
                        'complete and file, so what is recorded here is the state of the employer '
                        'account. The pre-employment and annual queries asked of those drivers, '
                        'and the violation and return-to-duty reporting the company owes, all '
                        'depend on it.'
 WHERE subject = 'company' AND code = 'CLEARINGHOUSE_REGISTRATION' AND effectiveto IS NULL;

-- Nothing points at it any more, and leaving it active invites somebody to file a document against
-- a requirement answered by the state of an account at FMCSA.
UPDATE credentialtypes SET active = 0 WHERE code = 'CLEARINGHOUSE_REGISTRATION';
