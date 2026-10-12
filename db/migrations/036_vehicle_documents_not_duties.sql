-- ################################################################################################
-- # 036 - the vehicle catalog lists documents, not duties.
-- #
-- # Three rows from 035 named an obligation with no paper behind it:
-- #   EMERGENCY_EQUIPMENT  49 CFR 393.95 sets what must be carried (extinguisher rating, visual
-- #                        charge indicator, mounting, warning devices) and demands no record. The
-- #                        record is the daily inspection report, where 396.11(a)(1)(xi) lists
-- #                        emergency equipment as one of the items checked. Folded into the DVIR and
-- #                        the daily log, and dropped.
-- #   USDOT_MARKING        displaying the number is a marking, not a document, and the company's
-- #                        USDOT registration row already says the number must appear on the vehicle.
-- #   PART38_SPECS         the paper that proves it is the manufacturer's or converter's
-- #                        certification, so the row is named after that.
-- ################################################################################################
UPDATE compliancedocs SET
    description = 'The driver''s written report on each vehicle operated, covering brakes, steering, lights, tires, horn, wipers, mirrors, coupling devices, wheels and rims, and emergency equipment - the extinguisher and warning devices required by 49 CFR 393.95. The repair certification goes on it where a defect is found.',
    legalcitation = '49 CFR 396.11(a)(1); 49 CFR 393.95'
    WHERE jurisdiction = 'US' AND subject = 'vehicle' AND code = 'DVIR';

UPDATE compliancedocs SET
    description = 'The habit part 396 imposes on commercial vehicles, kept voluntarily on vans: the same items a DVIR covers, including the fire extinguisher and warning devices. Brokers often require it.'
    WHERE jurisdiction = 'US' AND subject = 'vehicle' AND code = 'DAILY_INSPECTION_LOG';

UPDATE compliancedocs SET
    name = 'Accessible vehicle manufacturer or converter certification',
    description = 'The build or conversion paperwork showing the vehicle meets Part 38: lift rated 600 lb and interlocked so the vehicle cannot move unless stowed, securement area 30 x 48 in, lap and shoulder belts.'
    WHERE jurisdiction = 'US' AND subject = 'vehicle' AND code = 'PART38_SPECS';

DELETE FROM compliancedocs WHERE jurisdiction = 'US' AND subject = 'vehicle' AND code IN ('EMERGENCY_EQUIPMENT', 'USDOT_MARKING');
