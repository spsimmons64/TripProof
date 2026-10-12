-- ################################################################################################
-- # 012 - fee schedule: what TripProof charges for each screening service it orders for a customer.
-- # price NULL = not set yet.
-- ################################################################################################
CREATE TABLE IF NOT EXISTS feeschedule (
    recordid   VARCHAR(36)   NOT NULL,
    code       VARCHAR(32)   NOT NULL,
    name       VARCHAR(100)  NOT NULL,
    price      DECIMAL(10,2) NULL,
    active     TINYINT(1)    NOT NULL DEFAULT 1,
    sortorder  INT           NOT NULL DEFAULT 0,
    added      DATETIME      NOT NULL DEFAULT UTC_TIMESTAMP(),
    updated    DATETIME      NULL,
    PRIMARY KEY (recordid),
    UNIQUE KEY ux_feeschedule_code (code),
    CONSTRAINT ck_feeschedule_price CHECK (price IS NULL OR price >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO feeschedule (recordid, code, name, sortorder) VALUES
  ('fee00000-0001-4a00-9000-000000000001', 'MVR',           'Motor Vehicle Record (MVR)', 1),
  ('fee00000-0001-4a00-9000-000000000002', 'CDLIS',         'CDLIS Driver Check', 2),
  ('fee00000-0001-4a00-9000-000000000003', 'PSP',           'Pre-Employment Screening Program (PSP)', 3),
  ('fee00000-0001-4a00-9000-000000000004', 'CLEARINGHOUSE', 'FMCSA Clearinghouse Query', 4),
  ('fee00000-0001-4a00-9000-000000000005', 'BACKGROUND',    'Background Check', 5);
