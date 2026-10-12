-- How it is billed follows from who pays.
--
-- `billingmethod` asked a question the schedule already answers. Private pay is billed to the
-- passenger; a transportation broker takes its own invoice; Medicaid and a commercial payer
-- take a claim; a flat contract is a flat contract. Adding Flat Contract as a payer type
-- closed the last case where the two could differ - before that, a facility on an agreed
-- price and an insurer taking a claim were one type and only this field told them apart.
--
-- So it is computed from the payer type (rates.BILLED_AS) rather than stored. A stored copy
-- of something always derived is a second place for one fact, free to disagree with the
-- first - which is what `payer` and `billtoid` were before they went the same way.
--
-- If a commercial payer ever has to be invoiced rather than claimed, the honest fix is a
-- fifth payer type, not putting the question back.

ALTER TABLE payerschedules DROP COLUMN IF EXISTS billingmethod;
