-- ################################################################################################
-- # 313 - may this driver, in this vehicle, take this trip - asked and kept.
-- #
-- # Every check is stored with what it was asked about, when, the decision, what blocked it, and
-- # the rules it read, so an assignment can be explained afterwards from the answer it was given.
-- # A check made in shadow is recorded and not enforced: the engine runs beside the gate in use
-- # until its answers have been compared and it is switched on.
-- ################################################################################################

CREATE TABLE IF NOT EXISTS tripeligibility (
  recordid      VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid     VARCHAR(36)  NOT NULL,
  driverid      VARCHAR(36)  NULL,
  vehicleid     VARCHAR(36)  NULL,
  legid         VARCHAR(36)  NULL,
  program       VARCHAR(24)  NULL,
  evaluatedfor  DATETIME     NOT NULL,     -- the moment the trip happens
  evaluatedon   DATETIME     NOT NULL,     -- the moment it was asked
  evaluatedby   VARCHAR(36)  NULL,
  decision      VARCHAR(16)  NOT NULL,     -- eligible | notqualified | needsreview
  blockers      JSON         NULL,
  warnings      JSON         NULL,
  rulesread     JSON         NULL,         -- rule codes and their legal review status
  shadow        TINYINT(1)   NOT NULL DEFAULT 0,
  KEY ix_tripeligibility (accountid, legid, evaluatedon),
  KEY ix_tripeligibility_driver (accountid, driverid, evaluatedon)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
