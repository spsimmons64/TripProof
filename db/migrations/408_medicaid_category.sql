-- ################################################################################################
-- # 408 - Medicaid is a category of its own.
-- #
-- # Six sources, each a separate answer to "why is this asked": MEDICAID, FEDERAL_NEMT, STATE_NEMT,
-- # COMPANY, BROKER_PAYER and FMCSA_DOT. A rule belongs to Medicaid when it reaches a driver,
-- # vehicle or company only through Medicaid - the federal safeguards of 42 U.S.C. 1396a(a)(87)
-- # and the OIG exclusion check, enrollment and NPI, and each State's own Medicaid NEMT program.
-- # A private pay trip then visibly skips all of them.
-- ################################################################################################

UPDATE compliancerules SET authoritycategory = 'MEDICAID'
 WHERE authoritycategory IN ('FEDERAL_NEMT', 'STATE_NEMT')
   AND (applieswhen LIKE '%company.medicaid%' OR applieswhen LIKE '%medicaidstates%');
