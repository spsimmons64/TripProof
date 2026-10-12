-- Three payer types.
--
-- Eight were a taxonomy of how American healthcare is funded; three are the distinctions a
-- transport company actually bills differently. A Medicare Advantage plan, a commercial
-- insurer, a workers' compensation carrier and an auto PIP claim are all commercial payers
-- as far as this company is concerned - the rates are contracted, the money comes from an
-- organisation, and the difference between them lives on the payer's own record, not in a
-- category used to pick a fee schedule.
--
-- A facility on a flat contract is likewise a commercial payer billed as a flat contract.
-- HOW it is billed was always the other field.
--
-- Nothing is remapped today - every payer on file is a broker - but the statement stands so
-- the data cannot outlive the list in code.

UPDATE payers SET category = 'commercial'
 WHERE category NOT IN ('broker', 'commercial', 'medicaid');

-- A schedule covering a type that no longer exists would price nobody. Same remap.
UPDATE payerschedules
   SET payerkinds = 'commercial'
 WHERE payerkinds IS NOT NULL
   AND payerkinds NOT IN ('broker', 'commercial', 'medicaid')
   AND FIND_IN_SET('broker', payerkinds) = 0
   AND FIND_IN_SET('commercial', payerkinds) = 0
   AND FIND_IN_SET('medicaid', payerkinds) = 0;
