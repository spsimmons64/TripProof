-- ################################################################################################
-- # 224 - the Level 2 screening was decided in two places, and the two disagreed.
-- #
-- # Driver Qualifications said "Not asked". The driver's own requirements showed it waiting on an
-- # answer from the company. Both were reporting truthfully about different machinery:
-- #
-- #   the ADOPTION control said the company had not adopted it, and
-- #   the CONDITION `company.level2` said nobody had answered whether a contract requires it.
-- #
-- # Two controls for one decision, and a user looking at two screens being told two things. The
-- # requirement is not a regulation - its own citation says F.S. 409.907(8)(a)4. does NOT require
-- # it of NEMT drivers - so what decides it is whether this company's contract asks for it, which
-- # is exactly what the adoption control on Driver Qualifications is for.
-- #
-- # So the condition goes and the adoption decides, like the eight contract requirements added in
-- # 217. The question it hung on is retired with it: nothing else reads `company.level2`, and a
-- # question nobody's answer changes anything about is a question worth not asking.
-- ################################################################################################

UPDATE compliancerules
   SET applieswhen = NULL, offered = 1,
       description = 'Level 2 screening under F.S. 435.04 - fingerprints through FDLE and the FBI. '
                     'F.S. 409.907(8)(a)4. does NOT require it of NEMT drivers, so where it is '
                     'asked for it is a broker or Community Transportation Coordinator asking '
                     'under a contract. Adopt it here if yours does.'
 WHERE subject = 'driver' AND code = 'FL_LEVEL2_DRIVER' AND effectiveto IS NULL;

UPDATE companyquestions SET active = 0 WHERE factname = 'company.level2';
