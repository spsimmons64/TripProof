-- ################################################################################################
-- # 111 - Chapter 14-90 follows the driver, like everything else about a driver.
-- #
-- # 107 hung the 14-90 duties off the company's answer about a CTC or transit contract. That is what
-- # decides whether the chapter reaches the COMPANY - 14-90.002(2) - but it is not what decides
-- # whether it reaches a particular driver. A covered bus transit system can run covered buses and
-- # sedans on the same day, and the driver in the sedan does not owe an FDOT 725-030-11 medical
-- # examination or a daily duty status record.
-- #
-- # The driver record has carried the right switch since long before any of this: "Driver will be
-- # operating covered busses in accordance with F.A.C. Chapter 14-90". So that is what these four
-- # now read, the same way Part 391 reads the commercial motor vehicle box beside it.
-- #
-- # The company question stays and keeps its own job: it is what the Transportation Disadvantaged
-- # testing records hang off, because F.A.C. 41-2.006(4)(a) is a duty on the operator's programme
-- # rather than on one driver's file.
-- ################################################################################################

UPDATE compliancerules
   SET applieswhen = '{"fact":"driver.chapter1490","is":true}'
 WHERE effectiveto IS NULL AND code IN
   ('FL_TRANSIT_MEDICAL', 'FL_LICENSE_STATUS_NOTICE', 'FL_SSPP_DRIVER_RECORDS',
    'FL_HOURS_OF_SERVICE');
