-- ################################################################################################
-- # 166 - the Clearinghouse caveat, cut to the part that warns.
-- #
-- # Migration 165 removed the whole note when only its first sentence was unwanted. "General
-- # consent for Clearinghouse limited queries" describes what the consent IS, which the row's own
-- # name already says. What is worth a warning band is the second sentence: that this consent does
-- # not stand in for the electronic consent the driver gives inside the FMCSA Clearinghouse before
-- # a full query can be run.
-- ################################################################################################

UPDATE compliancerules
   SET note = 'Does not replace the driver''s electronic consent in the FMCSA Clearinghouse for a '
              'full query.'
 WHERE subject = 'driver' AND code = 'CLEARINGHOUSE_CONSENT' AND effectiveto IS NULL;
