-- ################################################################################################
-- # 182 - the Florida transit medical goes where the federal one went.
-- #
-- # 179 moved the DOT medical certificate to `predrive`, because certifying somebody medically
-- # qualified is about putting them behind a wheel rather than about taking them on. The Florida
-- # 14-90 medical examination is the same examination answering the same question under a different
-- # authority - F.A.C. 14-90.0041 even lets one physical answer both - and it was left at `prehire`
-- # only because it was invisible until 181 made the Chapter 14-90 rules reach anybody.
-- #
-- # Two medical requirements standing at different stages would have meant a driver blocked from
-- # being hired by the state examination and not by the federal one, for the same fact.
-- ################################################################################################

UPDATE compliancerules
   SET duestage = 'predrive'
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'FL_TRANSIT_MEDICAL';
