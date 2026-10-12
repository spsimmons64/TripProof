-- ################################################################################################
-- # 156 - two different questions, which were being answered as one.
-- #
-- #   Can I put this driver in a vehicle today?
-- #   Is this driver's file complete?
-- #
-- # They are not the same question and they do not have the same consequence. The first is a hard
-- # stop: the law or the contract says this person may not drive, and dispatch must not assign
-- # them. The second is work the office owes somebody - real, auditable, and not a reason to leave
-- # a trip uncovered this afternoon.
-- #
-- # `blocking` was being used for both, and had drifted onto nearly every rule: a driver with no
-- # bloodborne pathogens certificate read exactly like a driver with an expired licence. When
-- # everything blocks, nothing does - the office learns to ignore the mark.
-- #
-- #   hardstop    an expired licence, an expired medical card, a prohibited drug and alcohol
-- #               status, an overdue query somebody may not drive without
-- #   deficiency  the I-9, the trainings, the policy receipts, the file itself
-- #
-- # `blocking` is kept and still means "this rule counts against the file", because it is what the
-- # existing screens read. `gate` is the new, narrower thing, and only it stops a trip.
-- ################################################################################################

ALTER TABLE compliancerules
    ADD COLUMN IF NOT EXISTS gate VARCHAR(16) NOT NULL DEFAULT 'deficiency' AFTER blocking;

-- Everything is a deficiency unless it is one of the few things that actually stops a driver.
UPDATE compliancerules SET gate = 'deficiency' WHERE subject = 'driver';

-- 49 CFR 391.11(b)(5) a valid licence; 391.43/391.45 medical qualification; 391.31 the road test;
-- 382.301 a negative pre-employment controlled substances result before safety-sensitive work;
-- 382.701 the Clearinghouse queries; 40.305 the return to duty. Each of these is a sentence that
-- says the person may not drive, not a sentence that says a file is untidy.
UPDATE compliancerules
   SET gate = 'hardstop'
 WHERE subject = 'driver' AND effectiveto IS NULL
   AND code IN ('DRIVER_LICENSE_COPY', 'MEDICAL_CERT', 'FL_TRANSIT_MEDICAL', 'ROAD_TEST',
                'MVR_PREEMPLOYMENT', 'MVR_ANNUAL', 'PREEMPLOYMENT_DRUG_TEST',
                'PRIOR_VIOLATION_RTD', 'CLEARINGHOUSE_PREEMP', 'CLEARINGHOUSE');
