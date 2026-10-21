-- A Florida rule says so.
--
-- `TRANSIT_VEHICLE_INSPECTION` is F.A.C. 14-90.009 - its own description opens "Florida
-- requires" - but it was filed with `jurisdiction = 'US'` and applied on `company.transit`
-- alone. A covered transit operator in Ohio would have been told to meet a Florida rule,
-- and the catalogue would have called it federal.
--
-- Fixed the way the seven Florida DRIVER rules already do it: the state on the rule, and the
-- state in the condition. Those two together are what keep a state rule inside its state -
-- the jurisdiction column is read by people, the condition is read by the engine, and only
-- the second one actually stops the rule reaching somebody.
--
-- The code keeps its name. The FL_ prefix the driver rules carry is a convention rather than
-- a mechanism, and renaming a rule somebody's determinations already point at buys nothing.

UPDATE compliancerules
   SET jurisdiction = 'FL',
       applieswhen = '{"all":[{"fact":"company.state","eq":"FL"},'
                     '{"fact":"company.transit","is":true}]}'
 WHERE code = 'TRANSIT_VEHICLE_INSPECTION' AND effectiveto IS NULL;

-- And registration and insurance are statutes, not regulations. They stay one unconditional
-- rule each - every state requires both, so there is nothing to condition on - and their
-- authority already reads "State law", which is the honest answer until a second state makes
-- the difference worth spelling out.
UPDATE compliancerules
   SET authoritytype = 'statute'
 WHERE code IN ('VEHICLE_REGISTRATION', 'VEHICLE_INSURANCE_CARD') AND effectiveto IS NULL;
