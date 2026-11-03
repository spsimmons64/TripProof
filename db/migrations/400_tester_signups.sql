-- ################################################################################################
-- # 400 - transport companies asking to test TripProof before it opens, from the public site.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS testersignups (
  recordid   VARCHAR(36)  NOT NULL PRIMARY KEY,
  company    VARCHAR(160) NOT NULL,
  name       VARCHAR(120) NOT NULL,
  email      VARCHAR(255) NOT NULL,
  phone      VARCHAR(40)  NULL,
  state      VARCHAR(8)   NULL,
  fleet      VARCHAR(16)  NULL,
  brokers    VARCHAR(400) NULL,
  note       VARCHAR(2000) NULL,
  ip         VARCHAR(64)  NULL,
  added      DATETIME     NOT NULL,
  KEY ix_testersignups_added (added)
);
