-- ################################################################################################
-- # 350 - from the legal review of the 12:04 release (2026-10-22).
-- ################################################################################################

-- DCH 910.2 asks for a completed SATISFACTORY inspection. An inspection report on file now counts
-- once its result is recorded as passed; a failed one fails, and stays in the history after a
-- later pass. The initial inspection in the window before service must be a passed one.
UPDATE compliancerules SET reviewrequired = 1,
       description = 'The Georgia Medicaid broker inspects each vehicle it approves before it enters service - no earlier than sixty days before - and again no later than six months after the last inspection (DCH 910.1, 910.2). Reaches a vehicle approved for a Georgia Medicaid line, from the date it entered that service. An inspection counts once its result is recorded as passed; a failed inspection fails, and a later passing one does not erase it.'
 WHERE code = 'GA_NET_VEHICLE_INSPECTION' AND accountid IS NULL AND effectiveto IS NULL;

-- Who certified a defect repaired or needing no repair: the TripProof user, beside the name they
-- gave of whoever did the work (49 CFR 396.11(a)(3)(ii) - the carrier or its agent certifies).
ALTER TABLE vehicledvirs ADD COLUMN IF NOT EXISTS certifiedby VARCHAR(36) NULL AFTER certifiedon;

-- The screening is answered by its recorded result, not by its having been read. Said in the rule,
-- so the change carries a new rule version and not only a line in the correction history.
UPDATE compliancerules
   SET description = CONCAT(description, ' The result is recorded against the screening - Eligible or Not Eligible - and Not Eligible fails whoever read it.')
 WHERE accountid IS NULL AND effectiveto IS NULL AND code IN ('FL_LEVEL1_DRIVER', 'ABUSE_REGISTRY_CHECK')
   AND description NOT LIKE '%Eligible or Not Eligible%';
