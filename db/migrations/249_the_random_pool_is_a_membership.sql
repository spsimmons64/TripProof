-- Who was in the random testing pool, and when.
--
-- 49 CFR 382.305. Three things were wrong, and they were one thing: nobody owned the answer to
-- "who is in the pool".
--
--   1. THERE WERE TWO POOLS. The rate denominator counted drivers whose operation is `cdl` or
--      `cdlheavy` and never looked at randompoolon. The driver's own requirement read
--      randompoolon and never looked at the operation. A CDL driver nobody had enrolled was
--      therefore IN the pool for the purpose of computing how many must be tested, and OUT of
--      it on their own file. Both numbers were printed, neither was labelled, and they could
--      not both be right.
--
--   2. MEMBERSHIP HAD NO END. randompoolon is one date with nothing to close it. Taking a driver
--      out meant clearing it, which erases that they were ever in - so the pool on the day of
--      last March's draw could not be reconstructed, which is the single question a 382.305 rate
--      audit asks.
--
--   3. POOL SIZE WAS TYPED IN. Every draw asked somebody to enter the pool size by hand next to
--      a screen that was separately computing one. Two answers to one question, on the same
--      dialog.
--
-- Membership is now a span, and it is the only definition. The rate denominator counts it, the
-- driver's requirement reads it, and the size recorded against a draw is counted from it on the
-- day of the draw rather than typed.
--
-- 382.305(b) asks for a percentage of the AVERAGE number of driver positions, not of the number
-- on hand today, and spans are what make that computable: average = member-days / days in the
-- period. app/randompool.py does that arithmetic and nothing else does.
--
-- drivers.randompoolon is left in place, untouched, as the record this was built from. Nothing
-- reads or writes it any more.

CREATE TABLE IF NOT EXISTS randompoolmembership (
  recordid    varchar(36)  NOT NULL,
  accountid   varchar(36)  NOT NULL,
  driverid    varchar(36)  NOT NULL,
  -- The day they went in. A driver may leave and come back - moved to non-safety-sensitive work
  -- and then back to driving - so this is one row per spell, not one per driver.
  joinedon    date         NOT NULL,
  -- NULL means still in. The last day of membership, inclusive.
  leftpoolon  date         DEFAULT NULL,
  reason      varchar(255) DEFAULT NULL,
  addedby     varchar(36)  DEFAULT NULL,
  added       datetime     NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (recordid),
  KEY ix_randompool_driver (accountid, driverid, joinedon),
  KEY ix_randompool_span (accountid, joinedon, leftpoolon),
  CONSTRAINT fk_randompool_account FOREIGN KEY (accountid) REFERENCES accounts (recordid),
  CONSTRAINT fk_randompool_driver  FOREIGN KEY (driverid)  REFERENCES drivers  (recordid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Every driver anybody actually enrolled, carried over as an open spell. Deliberately NOT every
-- CDL driver: the other pool counted those, and treating "this driver holds a CDL" as "somebody
-- put this driver in the pool" would be the software asserting a fact nobody recorded. A CDL
-- driver who was never enrolled now reads as outstanding on their own file, which is the truth
-- and is actionable.
INSERT INTO randompoolmembership (recordid, accountid, driverid, joinedon, reason)
SELECT UUID(), d.accountid, d.recordid, d.randompoolon,
       'Carried over from the driver record'
  FROM drivers d
 WHERE d.randompoolon IS NOT NULL
   AND d.deleted IS NULL
   AND NOT EXISTS (SELECT 1 FROM randompoolmembership m WHERE m.driverid = d.recordid);
