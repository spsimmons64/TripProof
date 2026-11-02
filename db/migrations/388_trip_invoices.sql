-- ################################################################################################
-- # 388 - private-pay invoices: one numbered invoice per trip, billed to the passenger. Not the
-- # `invoices` table, which is what TripProof charges its own customers.
-- #
-- # Who it was billed to is kept as it read on the day, so correcting a passenger's address later
-- # does not rewrite an invoice already issued. A trip billed again voids the old charge lines and
-- # gets a new number; the old invoice stays on file.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS tripinvoices (
    recordid     VARCHAR(36)   NOT NULL,
    accountid    VARCHAR(36)   NOT NULL,
    number       INT           NOT NULL,
    tripid       VARCHAR(36)   NOT NULL,
    billtoname   VARCHAR(160)  NOT NULL,
    billtoaddress VARCHAR(255) NULL,
    billtophone  VARCHAR(32)   NULL,
    amount       DECIMAL(12,2) NOT NULL,
    issuedon     DATE          NOT NULL,
    createdon    DATETIME      NOT NULL,
    createdby    VARCHAR(36)   NOT NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_tripinvoices_number (accountid, number),
    KEY ix_tripinvoices_trip (accountid, tripid)
);

ALTER TABLE tripcharges MODIFY batchid VARCHAR(36) NULL;
ALTER TABLE tripcharges ADD COLUMN IF NOT EXISTS invoiceid VARCHAR(36) NULL AFTER batchid;
ALTER TABLE trips ADD COLUMN IF NOT EXISTS billinvoiceid VARCHAR(36) NULL AFTER billbatchid;
