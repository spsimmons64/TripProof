-- ################################################################################################
-- # 333 - a driver's drug and alcohol program is always worked out, never set by hand.
-- #
-- # Part 382 where the driver operates a commercial motor vehicle or holds a CDL, the Florida CTD
-- # program where the company does transit work, otherwise none - eligibility.program(). The
-- # override on the driver record is gone, so whatever it held is cleared rather than left to
-- # decide silently. (On 2026-10-21 the only one set matched what is worked out.)
-- ################################################################################################

UPDATE drivers SET datprogram = NULL WHERE datprogram IS NOT NULL;
