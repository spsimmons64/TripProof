-- A prohibition stops the driver, on every screen that asks.
--
-- THE DEFECT. A driver with an open positive read as "PROHIBITED" on his own testing page and
-- "Eligible - Clear to drive" on the company dashboard at the same moment. Both were reading
-- the same database and reaching opposite conclusions, because they were asking different
-- things: the testing page asks eligibility.standing(), and the dashboard asks the compliance
-- ENGINE which of this driver's requirements are hard stops. The engine had never been told
-- that prohibitions exist.
--
-- That is the worst shape of bug this application can have. Every other screen that decides
-- whether somebody may drive - the dashboard roster, the trip checks, the driver's own banner -
-- goes through the engine, so all of them would have cleared a driver who is federally barred
-- from the vehicle.
--
-- The fix is one rule, so there is one answer. `driver.prohibited` is true while an uncleared
-- bar exists, and this rule is a HARD STOP the whole time it is. It does not appear on the
-- requirements list of a driver who has no prohibition - there is nothing to say about them -
-- and it cannot be satisfied by filing anything, because the only thing that lifts it is the
-- return-to-duty process in 49 CFR Part 40 Subpart O, which is worked through on the driver's
-- testing page and clears the bar there.

INSERT INTO compliancerules
  (recordid, accountid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, sourceurl, applieswhen, evidencekind, evidencesource, origin, extendable, blocking,
   gate, grouping, duestage, duetext, recurrence, warndays, sensitivity, retentionrule,
   effectivefrom, sortorder)
SELECT UUID(), NULL, 'DA_PROHIBITION', 'Removed from safety-sensitive functions',
       CONCAT('A driver who has tested positive, refused a test, or otherwise violated ',
              '49 CFR Part 382 must be removed from safety-sensitive functions immediately and ',
              'stays removed until the entire return-to-duty process is complete: evaluation by ',
              'a substance abuse professional, whatever that professional prescribes, the ',
              'professional''s report that it was completed, and a return-to-duty test that ',
              'comes back negative. Time does not lift it, a later negative test does not lift ',
              'it, and the employer cannot lift it. It is worked through on the driver''s drug ',
              'and alcohol testing page, and clearing it there clears this.'),
       'driver', 'regulation', 'FMCSA', 'US', '49 CFR 382.501; 49 CFR Part 40 Subpart O',
       'https://www.ecfr.gov/current/title-49/section-382.501',
       '{"fact":"driver.prohibited","is":true}',
       'process', 'prohibition', 'office', 0, 1,
       'hardstop', 'regulatory', 'predrive',
       'In force until the return-to-duty process is complete',
       'once', 0, 'restricted', '5 years - 49 CFR 382.401(b)', '2001-08-01', 2
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'DA_PROHIBITION');
