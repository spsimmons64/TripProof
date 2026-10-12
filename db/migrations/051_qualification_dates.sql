-- ################################################################################################
-- # 051 - dates on a qualification: when it was issued, and when it runs out.
-- #
-- # Some things in a driver's file are good until they are replaced; others go stale on a date, or
-- # after a period the company itself sets - an MVR rechecked every twelve months, a training
-- # certificate good for two years. The catalog knows which kinds expire and describes the usual
-- # cycle in words; the number is the company's to set, because their broker or their own policy
-- # decides it.
-- #
-- #   expires    1 when filing this asks for an expiry date
-- #   validdays  how long a filed copy is good for, when the copy does not print its own date;
-- #              filing prefills the expiry with issue date + validdays, and it can be overridden
-- ################################################################################################
ALTER TABLE accountqualifications
    ADD COLUMN expires   TINYINT(1) NOT NULL DEFAULT 0 AFTER requiredfor,
    ADD COLUMN validdays INT        NULL     AFTER expires;

UPDATE accountqualifications q
  JOIN compliancedocs c ON c.code = q.code AND c.subject = 'driver'
   SET q.expires = c.expires
 WHERE q.catalog = 1;
