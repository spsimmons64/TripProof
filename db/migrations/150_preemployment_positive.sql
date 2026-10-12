-- ################################################################################################
-- # 150 - what follows a positive pre-employment test, which is two different decisions.
-- #
-- # A verified positive on a pre-employment DOT test produces two things, and running them together
-- # is how systems get this wrong.
-- #
-- #   THE DOT DECISION, which is not the employer's. The applicant is prohibited from performing
-- #   DOT safety-sensitive functions until the return-to-duty process is completed. The employer
-- #   cannot decide otherwise, cannot retest next week, and a later negative pre-employment test
-- #   does not erase it. This is already modelled - it is `driverprohibitions`.
-- #
-- #   THE EMPLOYMENT DECISION, which IS the employer's. DOT does not say whether to hire anybody.
-- #   The company may decline the applicant, or keep them and let them work through return to duty.
-- #   Nothing in Part 40 or Part 382 prefers either.
-- #
-- # So this adds the second one, and it is stored as what it is: a decision somebody made on a day,
-- # not a status the regulation handed down. A screen that offers only "Failed - do not hire" is
-- # telling the user that DOT requires a termination it does not require.
-- #
-- # AND THE OBLIGATION THAT SURVIVES EITHER ANSWER
-- #
-- # Whichever way the employment decision goes - including "we are not hiring this person" - the
-- # employer must give the applicant information about DOT-qualified substance abuse professionals
-- # (49 CFR 40.287). It is owed to somebody who will never work here, which is exactly the kind of
-- # obligation that gets forgotten, so it is a column with a date in it rather than a habit.
-- ################################################################################################

ALTER TABLE driverprohibitions
    ADD COLUMN IF NOT EXISTS sapinfogivenon DATE        NULL AFTER sapname,
    ADD COLUMN IF NOT EXISTS sapinfogivenby VARCHAR(36) NULL AFTER sapinfogivenon,
    -- donothire | continue. NULL means nobody has decided yet, which is a real state: the result
    -- lands today and the company answers it tomorrow.
    ADD COLUMN IF NOT EXISTS decision       VARCHAR(16) NULL AFTER clearedby,
    ADD COLUMN IF NOT EXISTS decidedon      DATE        NULL AFTER decision,
    ADD COLUMN IF NOT EXISTS decidedby      VARCHAR(36) NULL AFTER decidedon;
