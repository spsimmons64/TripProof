-- ################################################################################################
-- # 143 - what must be true before hiring, and what must be true before driving.
-- #
-- # "Required before hiring" was doing two jobs. Some of these decide whether somebody may be taken
-- # on at all; others decide whether the person already taken on may yet get behind the wheel. They
-- # are different questions asked by different people on different days, and running them together
-- # puts things in front of a hiring decision that are not reasons to decline anybody.
-- #
-- #   prehire    can this person be hired            application, licence, MVR, Clearinghouse
-- #                                                  query, pre-employment test, screening
-- #   predrive   may they now drive                  medical qualification, road test
-- #   athire     owed once they are on the books     I-9, W-4, training
-- #   ongoing    owed for as long as they drive      annual review, annual query, random pool
-- #
-- # The road test is the clearest case: 49 CFR 391.31 asks for it before the person drives a
-- # commercial motor vehicle, and FMCSA is explicit that it may happen before hire - it is not a
-- # hiring condition, it is a driving one. Medical qualification is the same shape: 391.43 is about
-- # being physically qualified to drive, not about being employable.
-- #
-- # `predrive` was already allowed for in the code that decides what a hiring decision sees. It had
-- # simply never been used.
-- ################################################################################################

UPDATE compliancerules
   SET duestage = 'predrive'
 WHERE subject = 'driver'
   AND code IN ('ROAD_TEST', 'MEDICAL_CERT', 'FL_TRANSIT_MEDICAL');
