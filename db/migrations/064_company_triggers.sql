-- ################################################################################################
-- # 064 - the questions only the company can answer.
-- #
-- # Most of the catalog is conditional, and a good part of that turns on a fact about the operation
-- # rather than about the driver: whose money pays for the trips, which rules the operation runs
-- # under, how background checks are obtained. Until now every one of those was assumed true, so a
-- # driver's file listed requirements that may not reach the company at all.
-- #
-- # A trigger is one such question, asked once of the company and answered yes or no. A catalog item
-- # can name the trigger that turns it on; when the answer is no, the item is not asked of that
-- # company's drivers. An unanswered question counts as yes, so nothing silently disappears before
-- # anyone has said otherwise.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS compliancetriggers (
    code      VARCHAR(24)  NOT NULL,
    question  VARCHAR(160) NOT NULL,
    help      VARCHAR(400) NULL,
    sortorder INT          NOT NULL DEFAULT 0,
    PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO compliancetriggers (code, question, help, sortorder) VALUES
 ('MEDICAID_TRIPS', 'Carries Medicaid funded trips',
  'Turns on the federal Medicaid minimum driver requirements, including screening every driver '
  'against the federal exclusion lists.', 10);

CREATE TABLE IF NOT EXISTS accounttriggers (
    accountid VARCHAR(36) NOT NULL,
    code      VARCHAR(24) NOT NULL,
    answer    TINYINT(1)  NOT NULL,
    updated   DATETIME    NOT NULL DEFAULT UTC_TIMESTAMP(),
    updatedby VARCHAR(36) NULL,
    PRIMARY KEY (accountid, code),
    CONSTRAINT fk_accounttriggers_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE compliancedocs ADD COLUMN triggercode VARCHAR(24) NULL AFTER sourcecode;

UPDATE compliancedocs SET triggercode = 'MEDICAID_TRIPS'
 WHERE subject = 'driver' AND code = 'EXCLUSION_CHECK_DRIVER';
