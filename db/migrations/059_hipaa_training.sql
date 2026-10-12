-- ################################################################################################
-- # 059 - HIPAA training follows the company's standing, not the fact of carrying patients.
-- #
-- # HIPAA reaches covered entities and business associates. Transporting patients does not by itself
-- # make a company either one: depending on its agreements with a plan, a provider or a broker, and
-- # on how it handles protected health information, it may be a business associate, or HIPAA may not
-- # apply to it directly at all. Where it does apply, the workforce is trained on the privacy
-- # policies and procedures as necessary for their work.
-- ################################################################################################
UPDATE compliancedocs
   SET obligation    = 'conditional',
       appliesif     = 'The company is a covered entity or a business associate handling protected health '
                       'information',
       legalcitation = '45 CFR 164.530(b)(1); 45 CFR 164.308(a)(5)',
       renewal       = 'Periodic while it applies; annual is the common practice',
       validdays     = 365,
       description   = 'Training on the company''s own privacy policies and procedures, as necessary for the '
                       'work. Carrying patients does not by itself make a company a covered entity or a '
                       'business associate - its agreements with a plan, provider or broker and its handling '
                       'of protected health information decide that.'
 WHERE subject = 'driver' AND code = 'HIPAA_TRAINING_DRIVER';

UPDATE accountqualifications
   SET obligation = 'conditional'
 WHERE catalog = 1 AND code = 'HIPAA_TRAINING_DRIVER' AND obligation = 'required';
