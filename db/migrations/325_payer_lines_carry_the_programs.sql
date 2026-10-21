-- ################################################################################################
-- # 325 - one list of who the company carries for.
-- #
-- # Payers, Programs and Broker Contracts all said the same sentence three ways: "we carry rides for
-- # this payer, in this state, since this date." The contract row already holds every part of it -
-- # payer, state, program, dates - so it becomes THE line, kept from the Payers page, and the
-- # program a line belongs to is read off the payer's kind unless somebody says otherwise. The
-- # company's programs are no longer entered; they are whatever its active lines carry.
-- #
-- # Private pay has no payer row, so its line names none and carries the program itself.
-- #
-- # companyprograms is left in place, unread, so nothing written to it is lost.
-- ################################################################################################

ALTER TABLE companycontracts
  ADD COLUMN IF NOT EXISTS status VARCHAR(12) NOT NULL DEFAULT 'active' AFTER program;

-- Every line names its program, so the rules never have to guess one from the payer.
UPDATE companycontracts c
LEFT JOIN payers p ON p.recordid = c.payerid
SET c.program = CASE p.category
                  WHEN 'broker' THEN 'medicaid'
                  WHEN 'medicaid' THEN 'medicaid'
                  WHEN 'commercial' THEN 'commercialinsurance'
                  WHEN 'flatcontract' THEN 'facility'
                  ELSE 'privatepay' END
WHERE c.program IS NULL;

-- Each program recorded by hand becomes a line, unless a line already carries it in that state.
INSERT INTO companycontracts (recordid, accountid, broker, payerid, state, program, status,
                              effectivefrom, effectiveto, reviewed, added, addedby)
SELECT UUID(), g.accountid,
       CASE g.program WHEN 'privatepay' THEN 'PRIVATE PAY' ELSE UPPER(g.program) END,
       NULL, g.state, g.program, g.status, g.effectivefrom, g.effectiveto, 0, g.added, g.addedby
FROM companyprograms g
WHERE NOT EXISTS (SELECT 1 FROM companycontracts c
                  WHERE c.accountid = g.accountid AND c.program = g.program
                    AND (c.state <=> g.state));
