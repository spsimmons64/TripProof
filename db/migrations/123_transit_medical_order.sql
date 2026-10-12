-- ################################################################################################
-- # 123 - the transit medical sits with the medical it doubles up on.
-- #
-- # FDOT 725-030-11 is a second medical examination on top of the one 49 CFR 391.43 asks for, not a
-- # separate kind of work, and an office that has just filed one is holding the paperwork for the
-- # other. Kept eighty rows apart they read as unrelated; together they read as what they are.
-- ################################################################################################

UPDATE compliancerules
   SET sortorder = 16
 WHERE code = 'FL_TRANSIT_MEDICAL' AND subject = 'driver';
