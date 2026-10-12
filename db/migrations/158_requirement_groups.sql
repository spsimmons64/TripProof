-- ################################################################################################
-- # 158 - what kind of thing a requirement is, which is not the same as when it is due.
-- #
-- # The list was grouped by WHEN - before hiring, before driving, once hired. That is the right
-- # question for somebody deciding whether to take a person on, and the wrong one for somebody
-- # looking at a file and asking what sort of obligations are in it.
-- #
-- #   consent     the driver signs it, and nothing happens without their signature. These are the
-- #               ones where the office cannot simply go and do the thing - a Clearinghouse query
-- #               needs 382.703(a) consent first, a background check needs FCRA authorisation.
-- #   regulatory  a government says so - FMCSA, FDOT, OSHA, IRS, USCIS, AHCA, CMS.
-- #   company     this company's own policy, or a contract it signed. Real, and nobody is going to
-- #               fine you for it.
-- #
-- # It is a column rather than something worked out from the authority, because the three are a
-- # judgement about how the office reads the file, and a judgement should be editable with an
-- # UPDATE rather than a deploy.
-- ################################################################################################

ALTER TABLE compliancerules
    ADD COLUMN IF NOT EXISTS grouping VARCHAR(16) NOT NULL DEFAULT 'regulatory' AFTER gate;

UPDATE compliancerules SET grouping = 'regulatory' WHERE subject = 'driver';

-- What the driver puts their name to. The I-9 and the W-4 are signed too and are not consents:
-- they are federal forms, and they stay with the rest of the federal requirements.
UPDATE compliancerules
   SET grouping = 'consent'
 WHERE subject = 'driver' AND effectiveto IS NULL
   AND code IN ('CLEARINGHOUSE_CONSENT', 'SAFETY_PERFORMANCE_CONSENT', 'FCRA_FORMS',
                'DA_POLICY_RECEIPT', 'PHI_CONFIDENTIALITY', 'EMPLOYMENT_APPLICATION');

-- The company's own, and the ones a broker or a CTC contract brings with it.
UPDATE compliancerules
   SET grouping = 'company'
 WHERE subject = 'driver' AND effectiveto IS NULL
   AND (authoritytype IN ('policy', 'contract') OR code IN ('DQ_FILE', 'FL_LEVEL2_DRIVER'))
   AND grouping <> 'consent';
