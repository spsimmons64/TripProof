-- ################################################################################################
-- # 213 - Clearinghouse registration follows the drivers, not the fleet.
-- #
-- # 202 conditioned the employer's registration on `fleet.cdl_required` - does any vehicle on file
-- # need a CDL. That is the wrong question and it produced a flat contradiction inside one account:
-- # a driver recorded as operating a heavy CDL vehicle had all three Clearinghouse requirements
-- # reaching him, including the pre-employment query, while the company was told the registration
-- # did not reach it. A query cannot be run by an employer who is not registered, so TripProof was
-- # asking for something it had just said was unnecessary.
-- #
-- # 49 CFR 382.701 puts the duty on the EMPLOYER of drivers subject to Part 382, and 382.705 makes
-- # that employer the one who reports violations. Part 382 reaches the person who operates a
-- # commercial motor vehicle requiring a CDL. So the question is whether this company employs such
-- # a driver, which is a fact about the roster.
-- #
-- # The fleet is not a sound proxy for it. A CDL driver may be in a leased vehicle, in a customer's
-- # vehicle, or in one nobody has recorded yet - here, four drivers and one vehicle on file. The
-- # new fact reads the drivers with the same test `driver.cdl` uses, so the company view and the
-- # driver view cannot disagree again.
-- #
-- # The fleet test stays as an alternative rather than being dropped: a company that has bought a
-- # CDL vehicle must be registered before it can qualify anybody to drive it, and losing that would
-- # trade one gap for another.
-- ################################################################################################

UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"operation.interstate","is":true},'
                     '{"any":[{"fact":"company.cdldrivers","is":true},'
                             '{"fact":"fleet.cdl_required","is":true}]}]}',
       description = 'The company must be registered with the FMCSA Drug and Alcohol Clearinghouse '
                     'to run queries and to report violations. It reaches any company employing a '
                     'driver who operates a commercial motor vehicle requiring a CDL - the duty '
                     'follows the drivers, not the vehicles on file - and the pre-employment and '
                     'annual queries asked of those drivers cannot be run without it.'
 WHERE subject = 'company' AND code = 'CLEARINGHOUSE_REGISTRATION' AND effectiveto IS NULL;
