-- ################################################################################################
-- # 157 - the consent, named and cited as the regulation names and cites it.
-- #
-- # 49 CFR 382.701(b)(2) is the paragraph about the limited query itself. The driver's consent to
-- # it is 382.703(a), which is a different paragraph about a different thing, and a file that cites
-- # the wrong one sends an auditor to the wrong place.
-- ################################################################################################

UPDATE compliancerules
   SET name = 'Consent for Clearinghouse Query',
       citation = '49 CFR 382.703(a)'
 WHERE subject = 'driver' AND code = 'CLEARINGHOUSE_CONSENT' AND effectiveto IS NULL;
