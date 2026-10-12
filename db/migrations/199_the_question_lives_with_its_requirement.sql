-- ################################################################################################
-- # 199 - the English determination is made on the requirement, not on the information page.
-- #
-- # 198 put the field on Driver Information because that is where driver facts live. It is the
-- # wrong place: somebody working a requirement is in the requirement, and a determination hidden
-- # on another screen is a determination nobody makes. The description said so out loud, which is
-- # how it got noticed.
-- ################################################################################################

UPDATE compliancerules
   SET description = 'The driver must be able to read and speak English well enough to converse '
                     'with the public, understand highway traffic signs and signals, respond to '
                     'official inquiries, and make entries on reports and records. The carrier '
                     'makes this determination - there is no certificate to collect - so it is '
                     'recorded here, on the requirement itself.'
 WHERE subject = 'driver' AND code = 'ENGLISH_PROFICIENCY' AND effectiveto IS NULL;
