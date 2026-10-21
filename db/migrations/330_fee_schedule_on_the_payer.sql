-- ################################################################################################
-- # 330 - the payer names its fee schedule; a state line may override it.
-- #
-- # A schedule is a price list of one payer type - private pay, or a kind of payer - so a payer is
-- # offered only the schedules of its own type. The payer's choice is the company's own, kept beside
-- # its status for the payer (a shared payer is everybody's; what this company is paid by it is not).
-- # Private pay has no payer row and is kept under the key 'privatepay'.
-- #
-- # A state line names a schedule only where that state is paid differently; otherwise the payer's
-- # applies. The lines carried over from 329 become the payer's choice and are cleared.
-- ################################################################################################

-- Every schedule says its payer type. Those that named payers take the type of those payers.
UPDATE payerschedules s
SET s.payerkinds = (SELECT MIN(p.category) FROM schedulepayers sp
                    JOIN payers p ON p.recordid = sp.payerid WHERE sp.scheduleid = s.recordid)
WHERE s.privatepay = 0 AND s.payerkinds IS NULL;

ALTER TABLE accountpayers ADD COLUMN IF NOT EXISTS scheduleid VARCHAR(36) NULL AFTER contactemail;

INSERT INTO accountpayers (accountid, payerid, scheduleid, updated)
SELECT c.accountid, COALESCE(c.payerid, 'privatepay'), MIN(c.scheduleid), UTC_TIMESTAMP()
FROM companycontracts c WHERE c.scheduleid IS NOT NULL
GROUP BY c.accountid, COALESCE(c.payerid, 'privatepay')
ON DUPLICATE KEY UPDATE scheduleid = VALUES(scheduleid);

UPDATE companycontracts c
JOIN accountpayers ap ON ap.accountid = c.accountid AND ap.payerid = COALESCE(c.payerid, 'privatepay')
SET c.scheduleid = NULL
WHERE c.scheduleid = ap.scheduleid;
