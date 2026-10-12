-- A schedule says who it applies to.
--
-- Listing payers one by one does not survive scale. A company with seventy-five brokers
-- cannot tick seventy-five boxes, and worse: the seventy-sixth broker, added next month,
-- would be priced by nothing at all until somebody remembered to go back and tick it. A list
-- is a snapshot; what is wanted is a rule.
--
-- So a schedule covers ONE of three things:
--
--   privatepay   the passenger
--   payerkinds   every payer of a kind - all brokers, all facilities, all insurers
--   named        particular payers, which is the exception rather than the rule
--
-- And named beats kind. "All brokers at this card, except ModivCare who negotiated their
-- own" needs no splitting and no re-ticking: it is one card for the kind and one for the
-- name, and the name wins. That is precedence, not conflict - the same shape `rulesets`
-- already uses, where a state baseline is overridden by a broker's own requirements.
--
-- `payerkinds` is a comma list rather than a fourth table. The values are a closed set fixed
-- in code (rates.CATEGORIES), a schedule carries two or three of them, and FIND_IN_SET keeps
-- the lookup a single query. A join table would be more orthodox and would buy nothing here.

ALTER TABLE payerschedules
  ADD COLUMN IF NOT EXISTS payerkinds VARCHAR(255) NULL AFTER privatepay;
