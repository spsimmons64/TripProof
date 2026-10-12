-- Two more roles that are a person, not a document.
--
-- Both are required by name, and both are already printed on a policy TripProof publishes -
-- the HIPAA Security Risk Analysis Policy names a Security Official at section 4, and the
-- Bloodborne Pathogens Exposure Control Plan names a Plan Administrator. Until now those
-- lines could only be ruled, because the appointment had nowhere to live.
--
-- Named here the way the DER and the Safety Manager are: the requirement is answered by
-- choosing somebody who has a login, the appointment carries its own date, and the policy
-- prints whoever holds it rather than whatever somebody typed into the words.

INSERT INTO compliancerules
  (recordid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, applieswhen, evidencekind, evidencesource, origin, gate, grouping, duestage,
   duetext, recurrence, blocking, sortorder, effectivefrom, addedby)
SELECT UUID(), 'HIPAA_SECURITY_OFFICIAL', 'HIPAA Security Official',
       'Somebody in this company is responsible for developing and operating its security '
       'policies and procedures - the person who coordinates the risk analysis, keeps its '
       'documentation, chases the corrective actions and reports what matters to management. '
       '45 CFR 164.308(a)(2) requires the designation by name. Name them here and the '
       'security risk analysis policy prints them; there is nothing to upload.',
       'company', 'regulation', 'HHS Office for Civil Rights', 'US',
       '45 CFR 164.308(a)(2)',
       '{"fact":"company.hipaa","is":true}',
       'person', 'companyrole:security', 'office', 'deficiency', 'regulatory', 'ongoing',
       'Before electronic protected health information is handled', 'once', 1, 51,
       '2026-10-09', 'system'
WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'HIPAA_SECURITY_OFFICIAL');

INSERT INTO compliancerules
  (recordid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, applieswhen, evidencekind, evidencesource, origin, gate, grouping, duestage,
   duetext, recurrence, blocking, sortorder, effectivefrom, addedby)
SELECT UUID(), 'BBP_PLAN_ADMINISTRATOR', 'Bloodborne pathogens plan administrator',
       'Somebody in this company administers the exposure control plan: the person who '
       'arranges the training, sees that protective equipment is there to be used, arranges '
       'the hepatitis B vaccination and any post-exposure evaluation, keeps the records and '
       'reviews the plan each year. Name them here and the plan prints them; there is '
       'nothing to upload.',
       'company', 'regulation', 'OSHA', 'US',
       '29 CFR 1910.1030(c)(1)',
       '{"fact":"company.exposure","is":true}',
       'person', 'companyrole:bbpadmin', 'office', 'deficiency', 'regulatory', 'ongoing',
       'Before anybody is assigned to work with occupational exposure', 'once', 1, 52,
       '2026-10-09', 'system'
WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'BBP_PLAN_ADMINISTRATOR');
