-- ################################################################################################
-- # 109 - three rules that should have been in 106 and were not.
-- #
-- # Found by asking the obvious question: if a driver is put in a sixteen-seat bus, where is the
-- # Clearinghouse consent? The queries were seeded and the consent was not, which is the worst
-- # shape for a gap to take - the screen looked complete, and the missing item was the one that
-- # makes the others lawful. 49 CFR 382.701(b)(2) requires the driver's specific written consent
-- # before a limited query is run, and a query run without it is not a query, it is a problem.
-- #
-- # The other two are the same kind of oversight:
-- #
-- #   SAFETY_PERFORMANCE_HISTORY  106 seeded the driver's CONSENT to release it and never the
-- #                               investigation itself - the thing the consent is for. 391.23(d)
-- #                               and (e) put the duty on the carrier to ask the previous
-- #                               employers, within 30 days of hire, three years back.
-- #
-- #   RANDOM_TESTING_RECORDS      382.305. Being in the pool is not a document that arrives; it is
-- #                               a standing state, and the driver record already carries the date
-- #                               they were placed in it.
-- ################################################################################################

INSERT INTO compliancerules
  (recordid, code, name, subject, authoritytype, authority, jurisdiction, citation, applieswhen,
   evidencekind, evidencesource, reviewrequired, determination, blocking, duestage, recurrence,
   recurrencedays, sensitivity, retentionrule, effectivefrom, sortorder)
VALUES
  -- Part 391: the investigation the consent exists to permit.
  (UUID(), 'SAFETY_PERFORMANCE_HISTORY', 'Previous employer safety performance history', 'driver',
   'regulation', 'FMCSA', 'US', '49 CFR 391.23(d), (e)',
   '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cmv_federal","is":true}]}',
   'process', 'credential:SAFETY_PERFORMANCE', 0, 0, 1, 'prehire', 'perhire', NULL,
   'restricted', 'Secure file with controlled access - 49 CFR 391.53', '2000-01-01', 135),

  -- Part 382: the consent that has to exist before a query is run.
  (UUID(), 'CLEARINGHOUSE_CONSENT', 'Clearinghouse query consent - signed by the driver', 'driver',
   'regulation', 'FMCSA', 'US', '49 CFR 382.701(b)(2)',
   '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cdl_required","is":true}]}',
   'document', 'signature:CLEARINGHOUSE_CONSENT', 0, 0, 1, 'prehire', 'days', 365,
   'normal', NULL, '2020-01-06', 205),

  -- Part 382: membership of the random pool, which is a state rather than a document.
  (UUID(), 'RANDOM_TESTING_RECORDS', 'Random testing pool membership', 'driver', 'regulation',
   'FMCSA', 'US', '49 CFR 382.305',
   '{"all":[{"fact":"operation.interstate","is":true},{"fact":"fleet.cdl_required","is":true}]}',
   'process', 'poolmember', 0, 0, 1, 'ongoing', 'once', NULL,
   'restricted', '5 years - 49 CFR 382.401(b)', '2000-01-01', 240);
