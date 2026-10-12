-- ################################################################################################
-- # 103 - the qualification catalog is removed, and will be rebuilt.
-- #
-- # What is going, and why. The catalog modelled a requirement as a document type with one
-- # `requiredfor` flag - both, cdl or noncdl. That flag cannot express the case most of an NEMT
-- # fleet actually sits in: a vehicle that is a commercial motor vehicle under 49 CFR 390.5 because
-- # it carries more than eight passengers for compensation, driven by somebody who will never hold
-- # a CDL. Part 391 reaches that driver in full; Part 382 does not reach them at all. There was no
-- # value to set that says so.
-- #
-- # The same flag carried no room for the other facts that decide applicability either - interstate
-- # against intrastate, the vehicle's weight and seating, the payer, the broker - so the list could
-- # only ever be approximately right, and being approximately right about whether somebody may
-- # lawfully drive is not worth keeping.
-- #
-- # So the catalog goes, the company's copy of it goes, and each driver's row against it goes. What
-- # replaces it is a requirements engine where a requirement is its own record with its own
-- # applicability conditions, and a document is evidence for a requirement rather than the same
-- # thing as one.
-- #
-- # WHAT IS NOT TOUCHED. Every record of something that actually happened stays exactly where it
-- # is: driverlicenses, drivermvrs, annualreviews, driverreports, drugtests, driverprohibitions,
-- # credentials, documents, documentsignatures. None of those were qualification state; they are
-- # the evidence, and the new engine will read the same rows.
-- ################################################################################################

-- The trip rules generated from the catalog are stood down rather than deleted, because legchecks
-- from past evaluation runs still point at them and a run has to stay readable as it was decided.
-- Only the generated credential requirements go. The three structural checks in the same ruleset -
-- licence class against the vehicle, DOT prohibition, and whether the driving record has been
-- reviewed since it arrived - were never derived from the catalog and keep working.
UPDATE requirements r
  JOIN rulesets s ON s.recordid = r.rulesetid
   SET r.status = 'NO_REQUIREMENT_FOUND', r.updated = UTC_TIMESTAMP()
 WHERE s.family = 'ACCOUNT-DRIVER-QUALIFICATION'
   AND r.kind = 'credential'
   AND r.status = 'REQUIRED';

-- Each driver's state against the catalog. This table was also a second copy of facts held
-- properly elsewhere - a report's state lived here and in driverreports at once, which is how a
-- filed PSP could show grey - so nothing is lost by its going.
DROP TABLE IF EXISTS driverqualifications;

-- The company's own copy of the catalog, and its answers to the eight applicability questions.
DROP TABLE IF EXISTS accountqualifications;
DROP TABLE IF EXISTS accounttriggers;

-- The catalog itself: the 47 driver items, the 8 trigger questions, the 12 authorities they hang
-- off. The regulatory research behind these rows is not lost - it is written up in the driver
-- qualification matrix, with every citation read against its primary source.
DROP TABLE IF EXISTS compliancedocs;
DROP TABLE IF EXISTS compliancetriggers;
DROP TABLE IF EXISTS compliancesources;
