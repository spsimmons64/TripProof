-- ################################################################################################
-- # 203 - the SSPP follows the contract, not the mailing address.
-- #
-- # Same mistake 181 fixed on the driver side: the plan was conditioned on the company's state as
-- # well as on working under a transit contract, so an operator registered elsewhere and running
-- # Florida transit work was asked for nothing. The transit question already asks about a
-- # Community Transportation Coordinator, a continuous transit contract or FDOT funding - it is a
-- # Florida question, and answering it yes is the statement that Chapter 14-90 reaches you.
-- ################################################################################################

UPDATE compliancerules
   SET applieswhen = '{"fact":"company.transit","is":true}'
 WHERE subject = 'company' AND code = 'SSPP' AND effectiveto IS NULL;
