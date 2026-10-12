-- ################################################################################################
-- # 200 - one licence requirement, not two.
-- #
-- # 197 added DRIVER_LICENCE because a carrier with no Medicaid work had no licence requirement at
-- # all: the only one in the catalog was conditioned on Medicaid and cited to 42 U.S.C. 1396a. That
-- # gap was real. What 197 did about it was not - it left a Medicaid carrier looking at two rows
-- # about the same licence, both green from the same record, and the richer of the two dialogs
-- # sitting behind the wrong one.
-- #
-- # They are not quite the same obligation. 391.11(b)(5) is "the driver holds a current licence of
-- # the right class". 42 U.S.C. 1396a(a)(87)(B) is "a copy of it is in the file". But no screen
-- # needs to say that twice, and the second never happens without the first.
-- #
-- # So: the Medicaid rule carries both authorities and keeps its own dialog, which already shows
-- # every licence held, its class, its endorsements and its expiry. The 391.11 rule steps aside
-- # wherever that one applies, and covers everybody else.
-- ################################################################################################

UPDATE compliancerules
   SET citation = '49 CFR 391.11(b)(5); 42 U.S.C. 1396a(a)(87)(B)',
       authority = 'FMCSA / CMS',
       description = 'The driver must hold a current license of the class the vehicle requires, '
                     'and - because this company carries Medicaid funded trips - a copy of it '
                     'belongs in the file. TripProof reads the license records themselves, so the '
                     'requirement goes amber as the expiry approaches and stops the driver the day '
                     'it passes.'
 WHERE subject = 'driver' AND code = 'DRIVER_LICENSE_COPY' AND effectiveto IS NULL;

-- The same question for everybody the Medicaid rule does not reach.
UPDATE compliancerules
   SET applieswhen = '{"not":{"fact":"company.medicaid","is":true}}',
       note = 'Where the company carries Medicaid funded trips this is asked as part of '
              'Driver''s Licenses instead, which also wants a copy of the card on file.'
 WHERE subject = 'driver' AND code = 'DRIVER_LICENCE' AND effectiveto IS NULL;
