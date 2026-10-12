-- ################################################################################################
-- # 204 - the Designated Employer Representative is a person, not a document.
-- #
-- # 202 made it a credential, so the only way to answer it was to upload something. That is wrong
-- # on its own terms: 49 CFR 40.3 defines a DER as an EMPLOYEE the employer authorises to receive
-- # test results and to immediately remove a driver from safety-sensitive duty, and says plainly
-- # that a service agent cannot be one. The question is "who", and the answer is somebody with a
-- # login here.
-- #
-- # `companyroles` is built for more than this one. Supervisor reasonable-suspicion training under
-- # 382.603 is the next thing in, and it has the same shape: a named person holding a role, with a
-- # date they took it up and a date they gave it back. A role nobody holds is a role nobody can be
-- # found to have held, which is why the row is kept and dated rather than deleted.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS companyroles (
    recordid  VARCHAR(36) NOT NULL,
    accountid VARCHAR(36) NOT NULL,
    role      VARCHAR(16) NOT NULL,          -- der | supervisor
    userid    VARCHAR(36) NOT NULL,
    since     DATE        NOT NULL,
    until     DATE        NULL,              -- gave it back; the row stays
    addedby   VARCHAR(36) NULL,
    added     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (recordid),
    KEY ix_companyroles_live (accountid, role, until),
    CONSTRAINT fk_companyroles_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

UPDATE compliancerules
   SET evidencekind = 'person', evidencesource = 'companyrole:der',
       description = 'Somebody in this company must be authorised to receive test results from the '
                     'medical review officer and to immediately remove a driver from '
                     'safety-sensitive duty. 49 CFR 40.3 requires an employee of the company - a '
                     'consortium or third party administrator cannot hold the role. Name them '
                     'here; there is nothing to upload.'
 WHERE subject = 'company' AND code = 'DER_DESIGNATION' AND effectiveto IS NULL;

-- Nothing points at it any more, and leaving it in the list invites somebody to file a document
-- against a requirement that is answered by naming a person.
UPDATE credentialtypes SET active = 0 WHERE code = 'DER_DESIGNATION';
