-- A prohibited driver is not asked to be in the random testing pool.
--
-- 49 CFR 382.305 tests drivers who perform safety-sensitive functions. A driver removed from
-- those functions under 382.501 is not one: what they owe is the return-to-duty process, and
-- afterwards follow-up testing under 40.307, which is its own schedule and not random at all.
--
-- The rule was gated on reach.part382 alone, so the moment a prohibition took a driver out of
-- the pool - which the engine now does by itself - their own file started asking the office to
-- put them back. That is the software instructing somebody to enrol a driver who may not be
-- tested randomly, in the same list that says they may not drive.
--
-- Gated on the bar as well, it does the right thing in both directions: silent while the driver
-- is prohibited, and outstanding again the moment the bar lifts - which is the prompt to put
-- them back in, asked by the requirement rather than by a reminder nobody wrote.

UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"reach.part382","is":true},'
                     '{"fact":"driver.prohibited","is":false}]}'
 WHERE code = 'RANDOM_TESTING_RECORDS';
