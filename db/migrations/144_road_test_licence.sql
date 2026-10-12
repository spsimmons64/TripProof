-- ################################################################################################
-- # 144 - a licence copy answers the road test.
-- #
-- # 49 CFR 391.33(a)(1): in place of a road test, the employer may accept a copy of a valid
-- # commercial driver's licence - a state issues one only after a skills test, so the test has
-- # already been given by somebody whose business it is to give it. The certificate 391.31 would
-- # have produced is replaced by the licence itself (391.33(b)).
-- #
-- # Conditioned on the driver actually holding a commercial licence. An ordinary licence is issued
-- # after no such test and answers nothing here.
-- #
-- # WHAT THIS DOES NOT COVER
-- #
-- # 391.33(c) withholds the equivalence from drivers of double and triple trailers and of tank
-- # vehicles - those need the road test itself. The endorsements are on the licence record, but
-- # they are a string of letters rather than a fact the rule language can test, so this is not
-- # expressed here: a carrier running tankers or doubles should give the road test and file the
-- # certificate. Worth revisiting when endorsements become facts in their own right.
-- ################################################################################################

UPDATE compliancerules
   SET alternatesource = 'licencecopy',
       alternatewhen   = '{"fact":"driver.licenceclass","in":["A","B","C"]}'
 WHERE code = 'ROAD_TEST' AND subject = 'driver';
