-- ################################################################################################
-- # 078 - the DOT application for employment, named for what it is and triggered by what triggers it.
-- #
-- # 49 CFR 391.21: a person may not drive a commercial motor vehicle unless they have completed and
-- # furnished the employing carrier an application meeting that section, and 391.51(b)(1) requires
-- # that application to be in the driver qualification file.
-- #
-- # What turns it on is operating a vehicle Part 391 reaches - not holding a commercial licence. A
-- # non-CDL driver in a qualifying vehicle owes one; a CDL holder who only ever drives a sedan does
-- # not. That is exactly the question the driver's own switch asks ("will be operating Commercial
-- # Motor Vehicles in accordance with FMCSA 49 CFR 390.5"), so this hangs off that and nothing else.
-- #
-- # There is no government form: a carrier's own application satisfies the rule as long as it carries
-- # everything the section lists - which the online application does.
-- ################################################################################################
UPDATE compliancedocs
   SET name          = 'DOT/FMCSA Driver Application for Employment',
       obligation    = 'conditional',
       classification = 'conditional',
       requiredfor   = 'cdl',
       stage         = 'prehire',
       appliesif     = 'The driver operates a commercial motor vehicle subject to Part 391, as 49 CFR 390.5 '
                       'defines one - whether or not they hold a commercial license',
       legalcitation = '49 CFR 391.21; 49 CFR 391.51(b)(1)',
       whendue       = 'Before the driver operates a commercial motor vehicle',
       renewal       = 'One application per period of employment',
       retention     = 'Three years after employment ends (49 CFR 391.51(d))',
       description   = 'The application the rule requires: identifying and contact details, license '
                       'information, driving experience, accidents and violations, and previous '
                       'employment - reaching back ten years for employers the applicant drove a '
                       'commercial vehicle for. No government form exists; a carrier''s own application '
                       'satisfies the section when it carries everything the section lists.'
 WHERE subject = 'driver' AND code = 'EMPLOYMENT_APPLICATION';

UPDATE accountqualifications q
  JOIN compliancedocs c ON c.code = q.code AND c.subject = q.subject
   SET q.applies = 'cdl', q.stage = 'prehire'
 WHERE q.code = 'EMPLOYMENT_APPLICATION' AND q.updated IS NULL;
