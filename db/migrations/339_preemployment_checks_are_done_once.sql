-- ################################################################################################
-- # 339 - a pre-employment check is done once, at hire.
-- #
-- # Five pre-employment checks were set to renew - yearly, or "when the document expires" - which put
-- # them on the driver's Validity-Tracked Documents panel with a "next due" date that means nothing.
-- # What recurs after hire has its own rule, and stays as it is:
-- #   CLEARINGHOUSE_PREEMP  (382.701(a))   - the annual limited query is CLEARINGHOUSE (382.701(b))
-- #   MVR_PREEMPLOYMENT     (391.23(a)(1)) - the annual record and review is MVR_ANNUAL (391.25)
-- #   DHS_MVR               (pre-employment certified 7-year record) - the annual one is DHS_MVR_ANNUAL
-- #   DHS_PREEMP_DRUG, NONDOT_DRUG_SCREEN - a test result, which does not expire.
-- ################################################################################################

UPDATE compliancerules SET recurrence = 'once', recurrencedays = NULL
 WHERE code IN ('CLEARINGHOUSE_PREEMP', 'MVR_PREEMPLOYMENT', 'DHS_MVR', 'DHS_PREEMP_DRUG',
                'NONDOT_DRUG_SCREEN')
   AND accountid IS NULL AND effectiveto IS NULL;
