-- ################################################################################################
-- # 122 - named for the requirement, ordered the way an office works.
-- #
-- # "Copy of the driver's license" named the artefact rather than the requirement. What the detail
-- # screen actually shows is every licence the driver holds, in every state, with the copies filed
-- # against them - so the rule is named for that.
-- #
-- # The order now matches the order the work happens in: the application arrives first and is what
-- # everything else is checked against, then the licences it claims, then the medical certificate
-- # that says the holder may use them. The rest keep the order they had.
-- ################################################################################################

UPDATE compliancerules
   SET sortorder = 5
 WHERE code = 'EMPLOYMENT_APPLICATION' AND subject = 'driver';

UPDATE compliancerules
   SET name = 'Driver''s Licenses', sortorder = 10
 WHERE code = 'DRIVER_LICENSE_COPY' AND subject = 'driver';

UPDATE compliancerules
   SET name = 'Medical Certificate', sortorder = 15
 WHERE code = 'MEDICAL_CERT' AND subject = 'driver';
