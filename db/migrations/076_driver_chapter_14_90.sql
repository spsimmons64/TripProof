-- ################################################################################################
-- # 076 - which drivers are on covered buses.
-- #
-- # Chapter 14-90 reaches an operation and the vehicles in it, and a company can run both kinds: a
-- # van on Medicaid trips and a covered bus on a transit contract, with different drivers in each.
-- # Saying it at the company level was too blunt, so it is said per driver - and the four Chapter
-- # 14-90 requirements reach only the drivers it is said of.
-- ################################################################################################
ALTER TABLE drivers ADD COLUMN chapter1490 TINYINT(1) NULL AFTER operatescmv;
