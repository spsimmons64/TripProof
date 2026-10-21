-- "License", not "licence".
--
-- American spelling, in every word an operator or an auditor reads, and in every code the engine
-- matches on. The CFR says "license" - 49 CFR 383.23 is headed "Commercial driver's license", and
-- the card in a Florida driver's wallet says "DRIVER LICENSE" across the top. A requirements list
-- that spells it the English way beside a citation that does not is the software's accent showing.
--
-- The codes go with the words. DRIVER_LICENCE and LICENCE_FITS_VEHICLE are matched by name in the
-- engine, and the fact names (driver.licenceclass, driver.licenceaction) and evidence sources
-- (licence, licencecopy, licencematch) are matched by name too - so the catalog and the code are
-- respelled in the same breath, or neither of them resolves.
--
-- Left alone: schemamigrations.filename, which is the list of files already run and must keep
-- naming them as they are on disk.

-- The list of kinds a requirement may be names the misspelling, so it has to be respelled before
-- the rows are - and dropped first, because a CHECK cannot be redefined in place. Guarded: DDL
-- commits as it goes, so this file re-runs from the top if a later statement fails.
ALTER TABLE requirements DROP CONSTRAINT IF EXISTS ck_requirements_kind;

UPDATE requirements
   SET code = REPLACE(code, 'LICENCE', 'LICENSE'),
       kind = REPLACE(kind, 'licence', 'license')
 WHERE code LIKE '%LICENCE%' OR kind LIKE '%licence%';

ALTER TABLE requirements ADD CONSTRAINT ck_requirements_kind CHECK (
  `kind` in ('credential','vehiclemileage','vehicleage','driverage','licenseyears','tripevidence',
             'obligation','licenseclass','annualreview','eligibility'));

UPDATE compliancerules
   SET code            = REPLACE(code,            'LICENCE', 'LICENSE'),
       evidencesource  = REPLACE(evidencesource,  'licence', 'license'),
       alternatesource = REPLACE(alternatesource, 'licence', 'license'),
       applieswhen     = REPLACE(applieswhen,     'licence', 'license'),
       alternatewhen   = REPLACE(alternatewhen,   'licence', 'license'),
       name        = REPLACE(REPLACE(name,        'Licence', 'License'), 'licence', 'license'),
       description = REPLACE(REPLACE(description, 'Licence', 'License'), 'licence', 'license'),
       duetext     = REPLACE(REPLACE(duetext,     'Licence', 'License'), 'licence', 'license'),
       extendnote  = REPLACE(REPLACE(extendnote,  'Licence', 'License'), 'licence', 'license'),
       note        = REPLACE(REPLACE(note,        'Licence', 'License'), 'licence', 'license')
 WHERE code LIKE '%LICENCE%' OR name LIKE '%licence%' OR description LIKE '%licence%'
    OR duetext LIKE '%licence%' OR note LIKE '%licence%' OR extendnote LIKE '%licence%'
    OR applieswhen LIKE '%licence%' OR alternatewhen LIKE '%licence%'
    OR evidencesource LIKE '%licence%' OR alternatesource LIKE '%licence%';

UPDATE credentialtypes
   SET name        = REPLACE(REPLACE(name,        'Licence', 'License'), 'licence', 'license'),
       description = REPLACE(REPLACE(description, 'Licence', 'License'), 'licence', 'license')
 WHERE name LIKE '%licence%' OR description LIKE '%licence%';

-- activitylog is deliberately append-only - a trigger refuses UPDATE and DELETE - so the acts
-- already logged keep the name they were logged under. Anything reading the log for filed license
-- copies has to accept both spellings, which is the price of a log that cannot be rewritten.

-- A past evaluation keeps a copy of the rule it ran against, so the result can be read back years
-- later. Respelling it changes no decision and keeps the reading consistent with the catalog.
UPDATE evaluationruns
   SET rulesnapshot = REPLACE(REPLACE(rulesnapshot, 'Licence', 'License'), 'licence', 'license')
 WHERE rulesnapshot LIKE '%licence%';
