-- Where a payer is, and what was signed with it.
--
-- An address because a payer is an organisation you correspond with: appeals, claim
-- enquiries and paper remittances all go somewhere, and "which Aetna" is a real question
-- once a company bills three of them. The field names are the ones the company profile
-- already uses - address1, city, state, zip - so one address looks like another everywhere
-- in the product.
--
-- And the contract, because the rates on a schedule are a copy of what the contract says.
-- When a payer underpays, the question is always "what did we agree", and the answer should
-- be one click from the payer rather than in somebody's mailbox.

ALTER TABLE payers
  ADD COLUMN IF NOT EXISTS address1    VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS address2    VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS city        VARCHAR(64)  NULL,
  ADD COLUMN IF NOT EXISTS state       CHAR(2)      NULL,
  ADD COLUMN IF NOT EXISTS zip         VARCHAR(10)  NULL,
  ADD COLUMN IF NOT EXISTS phone       VARCHAR(32)  NULL,
  -- Who to ring about a claim. A named person beats a switchboard when a denial is being
  -- argued, and it is the one thing nobody writes down.
  ADD COLUMN IF NOT EXISTS contactname  VARCHAR(96) NULL,
  ADD COLUMN IF NOT EXISTS contactemail VARCHAR(255) NULL;

-- Contracts, amendments, rate sheets. A list rather than a column on the payer: a contract
-- is amended, and the amendment does not replace the thing it amends.
--
-- The file itself goes in `documents` like every other file this product holds - encrypted
-- at rest, deduplicated by hash, downloaded through the one endpoint that logs who looked.
-- This table only says which payer it belongs to and what it is.
CREATE TABLE IF NOT EXISTS payerdocuments (
  recordid    VARCHAR(36)  NOT NULL,
  accountid   VARCHAR(36)  NOT NULL,
  payerid     VARCHAR(36)  NOT NULL,
  documentid  VARCHAR(36)  NOT NULL,
  -- What this paper is: "2026 contract", "Rate amendment 3". Free text, because the next
  -- contract will be called something nobody has a word for yet.
  title       VARCHAR(120) NOT NULL,
  -- When it takes effect and when it stops, where the paper says. Both optional: plenty of
  -- contracts are undated and pretending otherwise would put a guess on the record.
  effectivefrom DATE           NULL,
  effectiveto   DATE           NULL,
  note        VARCHAR(512)     NULL,
  addedby     VARCHAR(36)      NULL,
  added       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
  PRIMARY KEY (recordid),
  KEY ix_payerdocuments_payer (payerid, added),
  CONSTRAINT fk_payerdocuments_account
    FOREIGN KEY (accountid) REFERENCES accounts (recordid),
  CONSTRAINT fk_payerdocuments_payer
    FOREIGN KEY (payerid) REFERENCES payers (recordid),
  CONSTRAINT fk_payerdocuments_document
    FOREIGN KEY (documentid) REFERENCES documents (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
