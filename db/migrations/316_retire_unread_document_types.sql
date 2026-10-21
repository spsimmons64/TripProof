-- ################################################################################################
-- # 316 - document types nothing reads any more, retired.
-- #
-- # Each was the evidence for a rule that is now answered another way, and none has a record on
-- # file. Retired rather than deleted, so anything still pointing at one resolves:
-- #
-- #   TPA_AGREEMENT              the rule reads the adopted service agent policy
-- #   RANDOM_TESTING_PROGRAM     the rule reads the adopted random testing policy
-- #   BBP_EXPOSURE_DETERMINATION the rule reads the signed exposure determination
-- #   LOCAL_VEHICLE_PERMIT       the county permit rule reads the company's COPEC
-- #   SAFETY_TRAINING            only an inactive trip-level requirement named it
-- #
-- # MISCELLANEOUS stays: it is the "anything else" choice when a document is uploaded.
-- ################################################################################################

UPDATE credentialtypes SET active = 0, updated = UTC_TIMESTAMP()
 WHERE accountid IS NULL
   AND code IN ('TPA_AGREEMENT', 'RANDOM_TESTING_PROGRAM', 'BBP_EXPOSURE_DETERMINATION',
                'LOCAL_VEHICLE_PERMIT', 'SAFETY_TRAINING')
   AND NOT EXISTS (SELECT 1 FROM credentials c WHERE c.credentialtypeid = credentialtypes.recordid
                     AND c.deleted IS NULL);
