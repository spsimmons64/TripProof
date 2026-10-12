-- The bloodborne pathogens exposure determination is an assessment, not a certificate.
--
-- 29 CFR 1910.1030(c)(2) asks the employer to write down which job classifications have
-- occupational exposure to blood or other potentially infectious material, which tasks within
-- them create it, and - the part everybody gets wrong - to decide that WITHOUT regard to the
-- personal protective equipment people are given. The question is what the work exposes
-- somebody to, not what they wear against it.
--
-- It asked for a file to upload, which meant the carrier had to find the words from somewhere.
-- It is now the seventh published policy: TripProof writes the assessment, the company adopts
-- it with a date, and the three tables - all exposed, some exposed, none exposed - are ruled
-- rows it completes for its own classifications.

UPDATE compliancerules
   SET evidencekind = 'policy',
       evidencesource = 'policy:BBP_EXPOSURE_DETERMINATION'
 WHERE code = 'BBP_EXPOSURE_DETERMINATION';
