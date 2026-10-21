-- ################################################################################################
-- # 326 - whether THIS company still works with a shared payer.
-- #
-- # A shared broker is one row every company points at, so its own Active flag is the platform's:
-- # retiring it there retires it for everyone. Whether one company has stopped carrying for it is
-- # that company's own fact, kept here. A company's own payers keep using payers.active.
-- #
-- # Inactive takes the payer out of booking and pricing, and its state lines stop counting - they
-- # no longer decide the company's programs or match a trip to a contract. Nothing is deleted, so
-- # making it active again puts everything back.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS accountpayers (
  accountid  VARCHAR(36) NOT NULL,
  payerid    VARCHAR(36) NOT NULL,
  active     TINYINT(1)  NOT NULL,
  updated    DATETIME    NOT NULL,
  updatedby  VARCHAR(36) NULL,
  PRIMARY KEY (accountid, payerid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
