-- ################################################################################################
-- # 403 - messages sent from the Contact page on the public site.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS contactmessages (
  recordid   VARCHAR(36)   NOT NULL PRIMARY KEY,
  topic      VARCHAR(16)   NOT NULL,
  name       VARCHAR(120)  NOT NULL,
  company    VARCHAR(160)  NULL,
  email      VARCHAR(255)  NOT NULL,
  phone      VARCHAR(40)   NULL,
  message    VARCHAR(4000) NOT NULL,
  ip         VARCHAR(64)   NULL,
  added      DATETIME      NOT NULL,
  KEY ix_contactmessages_added (added)
);
