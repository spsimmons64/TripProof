-- ################################################################################################
-- # 212 - the MCS-150 biennial update, on FMCSA's schedule rather than on a count of days.
-- #
-- # The rule said `days 730` - two years from whenever the last one was filed. That is not what
-- # 49 CFR 390.19(b) says. The schedule belongs to the USDOT NUMBER: the last digit fixes the month
-- # (1 January through 9 September, 0 October) and the parity of the next-to-last digit fixes the
-- # year (odd digit, odd-numbered years). Filing early does not move the deadline and filing late
-- # does not push the next one out, so a day count drifts further from the real date every cycle -
-- # and a carrier told the wrong month has its USDOT number deactivated for missing the right one.
-- #
-- # It could not have been right in any case, because TripProof did not hold the number. Nothing on
-- # `accounts` carried it and nothing in the application asked. So the arithmetic had no input and
-- # 730 days was not a simplification, it was the only thing available.
-- #
-- # The filing itself becomes a record of its own rather than a credential. What is wanted is the
-- # day it was filed and the proof, and the next due date is not a property of the filing at all -
-- # it is read off the number. A credential with an expiry date would invite somebody to type one.
-- #
-- # The MC number and the trading name come along because the official form asks for both and the
-- # worksheet cannot be filled without them.
-- ################################################################################################

ALTER TABLE accounts
  ADD COLUMN IF NOT EXISTS usdot    VARCHAR(12)  NULL AFTER ein,
  ADD COLUMN IF NOT EXISTS mcnumber VARCHAR(12)  NULL AFTER usdot,
  ADD COLUMN IF NOT EXISTS dba      VARCHAR(128) NULL AFTER name;

-- `recurrence` was sized for the words already in it. "usdotbiennial" is longer than any of them.
ALTER TABLE compliancerules MODIFY COLUMN recurrence VARCHAR(16) NULL;

CREATE TABLE IF NOT EXISTS mcs150filings (
    recordid   VARCHAR(36) NOT NULL,
    accountid  VARCHAR(36) NOT NULL,
    filedon    DATE        NOT NULL,
    -- How it went in. FMCSA prefers the Portal; the form and the post are still accepted.
    method     VARCHAR(8)  NOT NULL,          -- portal | form | mail
    documentid VARCHAR(36) NULL,              -- the receipt, or the signed form
    note       VARCHAR(512) NULL,
    filedby    VARCHAR(36) NULL,
    added      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted    DATETIME    NULL,
    PRIMARY KEY (recordid),
    KEY ix_mcs150filings_account (accountid, filedon),
    CONSTRAINT fk_mcs150filings_account FOREIGN KEY (accountid) REFERENCES accounts (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

UPDATE compliancerules
   SET evidencekind   = 'filing',
       evidencesource = 'mcs150',
       recurrence     = 'usdotbiennial',
       recurrencedays = NULL,
       duetext        = 'In the month set by the last digit of the USDOT number, every two years',
       description    = 'Carrier registration must be updated with FMCSA every two years whether '
                        'or not anything has changed. 49 CFR 390.19(b) sets the month from the '
                        'last digit of the USDOT number and the year from the digit before it, so '
                        'TripProof works the date out from the number rather than counting two '
                        'years from the last filing. Letting it lapse deactivates the USDOT number.'
 WHERE subject = 'company' AND code = 'MCS150' AND effectiveto IS NULL;

-- Nothing points at it any more, and leaving it in the list invites somebody to file a document
-- against a requirement that is answered by recording when the update went in.
UPDATE credentialtypes SET active = 0 WHERE code = 'MCS150';
