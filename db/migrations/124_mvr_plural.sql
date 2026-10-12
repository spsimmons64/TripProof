-- ################################################################################################
-- # 124 - records, plural.
-- #
-- # 49 CFR 391.23(a)(1) asks for a record from each licensing authority the driver held a licence
-- # with over the window, so a driver who moved states owes several. The singular name was the same
-- # mistake the screen used to make: one record on file and a silence reading as complete.
-- ################################################################################################

UPDATE compliancerules
   SET name = 'Motor Vehicle Records'
 WHERE code = 'MVR_PREEMPLOYMENT' AND subject = 'driver';
