-- ################################################################################################
-- # 395 - the passenger's signature at the drop-off, taken on the driver's phone; or, where there
-- # is none, why not, in the driver's words. One per leg.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS legsignatures (
  legid      VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid  VARCHAR(36)  NOT NULL,
  driverid   VARCHAR(36)  NULL,
  image      MEDIUMTEXT   NULL,          -- a PNG, as a data URL
  nosignature VARCHAR(24) NULL,          -- why there is no signature
  note       VARCHAR(400) NULL,
  signedon   DATETIME     NOT NULL,
  KEY ix_legsignatures_account (accountid)
);
