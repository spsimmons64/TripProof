-- ################################################################################################
-- # 208 - a company may edit its own policy, and the file says whose words they are.
-- #
-- # 207 published the two policies as templates nobody could change. The reasoning was sound - our
-- # words can be corrected for every customer at once when 49 CFR moves, and bespoke legal prose
-- # per account cannot - but it is not our call to make. A company's policy is the company's.
-- #
-- # So the published text becomes the STARTING POINT. Edit it and the edited copy is what renders,
-- # what prints, and what a driver receives. The merge fields still fill, so the DER still comes
-- # from the appointment rather than from something typed in and forgotten.
-- #
-- # What is kept is the honesty: a company on its own wording is told it no longer tracks our
-- # updates, and can put the published text back with one action. A silent fork is the thing worth
-- # avoiding, not a fork.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS companypolicies (
    accountid VARCHAR(36) NOT NULL,
    code      VARCHAR(32) NOT NULL,         -- DRUG_POLICY | WORKPLACE_POLICY
    text      LONGTEXT    NOT NULL,
    basedon   VARCHAR(16) NULL,             -- the published version it was forked from
    updated   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedby VARCHAR(36) NULL,
    PRIMARY KEY (accountid, code),
    CONSTRAINT fk_companypolicies_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
