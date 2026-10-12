-- The SSPP driver records are Driver Files, and nothing else.
--
-- This rule has now been in two places and belonged in neither. It started on the driver as a
-- document to upload; today it moved to the company as a check across the driver records. Both
-- shapes were a row that reported on records already held and already listed, on a screen whose
-- whole job is to list them - Driver Files.
--
-- F.A.C. 14-90.004(3)(g) is not being ignored. It asks the transit system to KEEP the driver
-- background, qualification, training and duty records for four years, and keeping them is what
-- Driver Files is. A separate requirement saying "those records exist" adds a row to a list and
-- nothing to the file.
--
-- The System Safety Program Plan itself - the written plan under F.A.C. 14-90.004 - is a real
-- document and stays exactly as it is. This only removes the rule that reported on the driver
-- records behind it.

UPDATE compliancerules
   SET effectiveto = CURDATE(),
       note = 'Retired. The records it reported on are held and listed in Driver Files, which '
              'is what keeping them means. The SSPP document itself is unaffected.'
 WHERE code IN ('FL_SSPP_RECORDKEEPING', 'FL_SSPP_DRIVER_RECORDS');
