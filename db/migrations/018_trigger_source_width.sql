-- ################################################################################################
-- # 018 - requirements.triggersource holds 'suggested' (derived, never enforced) or 'manual'
-- # (confirmed by a person). Widen it for 'suggested'.
-- ################################################################################################
ALTER TABLE requirements MODIFY COLUMN triggersource VARCHAR(12) NULL;
