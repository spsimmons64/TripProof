-- Every trip decision records the engine version that made it, beside the rule versions it read
-- (rulesread), so a decision can be reproduced against the rules and the evaluator of its day.
ALTER TABLE tripeligibility ADD COLUMN IF NOT EXISTS engineversion VARCHAR(16) NULL AFTER rulesread;
