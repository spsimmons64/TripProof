-- ################################################################################################
-- # 343 - whether a license is a CDL is asked of the license, not read off its class letter.
-- #
-- # Georgia's ordinary license is a Class C, and some States issue non-commercial Class A and B
-- # licenses, so "Class C" proves nothing. The license now says commercial yes, no, or not said.
-- ################################################################################################

ALTER TABLE driverlicenses
  ADD COLUMN IF NOT EXISTS commercial TINYINT(1) NULL AFTER classification;

-- Florida issues Classes A, B and C only as commercial licenses; its ordinary license is Class E
-- (F.S. 322.54). Those records can be answered. Every other State's stay "not said" until
-- somebody looks at the card.
UPDATE driverlicenses SET commercial = 1
 WHERE commercial IS NULL AND state = 'FL' AND UPPER(classification) IN ('A', 'B', 'C');
UPDATE driverlicenses SET commercial = 0
 WHERE commercial IS NULL AND state = 'FL' AND UPPER(classification) IN ('E', 'M');

-- 49 CFR 391.33: a CDL stands in for the road test. Now a license recorded as a CDL, for a driver
-- whose work calls for one - not any Class A, B or C.
UPDATE compliancerules
   SET alternatewhen = '{"all":[{"fact":"driver.cdl","is":true},{"fact":"driver.licensecommercial","is":true}]}'
 WHERE code = 'ROAD_TEST' AND accountid IS NULL AND effectiveto IS NULL;

-- DCH 914.2.1: a Georgia license, or one from the bordering state the driver lives in.
UPDATE compliancerules SET evidencesource = 'license:georgia'
 WHERE code = 'GA_NET_LICENSE' AND accountid IS NULL AND effectiveto IS NULL;
