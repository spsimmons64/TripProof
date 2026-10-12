-- ################################################################################################
-- # 228 - one background screening, ordered, with a choice of how deep.
-- #
-- # 217 shipped the criminal background check and the sex offender registry check as two separate
-- # requirements. They are not two jobs: nobody runs one without the other, no vendor sells them
-- # apart, and a file carrying one and not the other answers nothing anybody asks. Two rows for one
-- # order is two things to adopt, two things to chase and two things to go green.
-- #
-- # So they become one requirement answered the way the PSP report and the CDLIS check already are:
-- # ordered, outstanding until it comes back, then read. `driverreports` carries that shape
-- # already - ordered, received, outcome, reviewed, with the report attached - which is why this
-- # introduces no new machinery, only a new code and the tier that was ordered.
-- #
-- # The tier is the company's choice at the moment of ordering, and the file has to say which was
-- # bought: a Core screening that came back clear is not evidence that a Complete screening would
-- # have, and an auditor asking "what did you actually run on this driver" needs the answer.
-- #
-- # Whatever either old rule was adopted for carries across. A company that asked for a background
-- # check on every driver yesterday is still asking for one today.
-- ################################################################################################

ALTER TABLE driverreports
  ADD COLUMN IF NOT EXISTS tier VARCHAR(12) NULL AFTER code;

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype, authority,
                             citation, applieswhen, evidencekind, evidencesource, origin,
                             extendable, offered, reviewrequired, determination, blocking, gate,
                             grouping, duestage, duetext, recurrence, warndays, note, sortorder,
                             effectivefrom)
SELECT UUID(), 'driver', 'BACKGROUND_SCREENING', 'Background screening',
       'A criminal history and sex offender registry search on the driver, ordered through Certn. '
       'Core covers the national criminal and sex offender registry searches; Complete adds the '
       'wider county, federal and identity checks. Not a federal requirement for a non-CDL driver '
       '- brokers and payers ask for it, and which depth they ask for is in the contract. The file '
       'records which was ordered, because a Core search coming back clear is not evidence that a '
       'Complete one would have.',
       'contract', 'Broker and payer contracts', NULL, NULL,
       'query', 'report:BACKGROUND_SCREENING', 'thirdparty', 1, 1, 0, 1, 1, 'deficiency',
       'company', 'prehire', NULL, 'once', 30, NULL, 311, CURRENT_DATE
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules
                    WHERE subject = 'driver' AND code = 'BACKGROUND_SCREENING'
                      AND effectiveto IS NULL);

-- Carry the adoption across before the old rows go, so nothing a company asked for stops being
-- asked for. The wider of the two elections wins: somebody who wanted it of every driver on either
-- row wanted it of every driver.
INSERT INTO companyrulepolicy (accountid, rulecode, applyto, reason)
SELECT p.accountid, 'BACKGROUND_SCREENING',
       CASE WHEN MAX(p.applyto = 'alldrivers') THEN 'alldrivers'
            WHEN MAX(p.applyto = 'noncdl') THEN 'noncdl'
            WHEN MAX(p.applyto = 'cdl') THEN 'cdl'
            ELSE 'regulation' END,
       'Carried over when the criminal and sex offender checks became one screening'
  FROM companyrulepolicy p
 WHERE p.rulecode IN ('BACKGROUND_CHECK', 'SEX_OFFENDER_CHECK')
 GROUP BY p.accountid
ON DUPLICATE KEY UPDATE applyto = VALUES(applyto);

UPDATE compliancerules SET effectiveto = CURRENT_DATE
 WHERE subject = 'driver' AND effectiveto IS NULL
   AND code IN ('BACKGROUND_CHECK', 'SEX_OFFENDER_CHECK');

UPDATE credentialtypes SET active = 0 WHERE code IN ('BACKGROUND_CHECK', 'SEX_OFFENDER_CHECK');
