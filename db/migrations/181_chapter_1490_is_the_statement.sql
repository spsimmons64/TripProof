-- ################################################################################################
-- # 181 - the 14-90 tick is the statement. The company's address is not.
-- #
-- # Four rules carry Florida Chapter 14-90 obligations, and every one of them asked for TWO things:
-- # that the driver operates covered buses under 14-90, AND that the company's state is FL. The
-- # second condition is the company's mailing address, which is not what decides whether a Florida
-- # rule reaches an operation.
-- #
-- # The effect, found by auditing live data: an account registered in Kansas with a driver ticked
-- # "operating covered busses in accordance with F.A.C. Chapter 14-90" generated none of the
-- # Chapter 14-90 requirements. The tick did nothing, silently, and the requirements screen showed
-- # the federal half of a file that should have had both halves.
-- #
-- # The driver-level tick already IS the company saying 14-90 applies to this driver - it is a
-- # deliberate statement about how the person will be used, made on the driver's own record. A
-- # company does not tick it by accident, and an address in another state does not unsay it.
-- #
-- # Left alone on purpose: the rules conditioned on company.state together with Medicaid, Level 2
-- # or intrastate operation. Those really are about where the company works rather than about one
-- # driver's duties, and the state answer is the right question for them.
-- ################################################################################################

UPDATE compliancerules
   SET applieswhen = '{"fact":"driver.chapter1490","is":true}'
 WHERE subject = 'driver' AND effectiveto IS NULL
   AND code IN ('FL_TRANSIT_MEDICAL', 'FL_HOURS_OF_SERVICE', 'FL_SSPP_DRIVER_RECORDS');

UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"driver.chapter1490","is":true},'
                     '{"fact":"driver.licenceaction","is":true}]}'
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'FL_LICENSE_STATUS_NOTICE';
