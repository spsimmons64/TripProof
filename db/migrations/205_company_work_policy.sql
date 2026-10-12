-- ################################################################################################
-- # 205 - the company work policy, as a requirement rather than a loose document.
-- #
-- # The credential type has existed since early on and nothing ever asked for it, so a company
-- # could have one, not have one, or have one that lapsed, and no screen would say. The drug and
-- # alcohol policy got its requirement in 202; this is its pair.
-- #
-- # Not a regulation, and the row says so: the authority is the company itself. It is a deficiency
-- # rather than a hard stop for the same reason - nobody is grounded over it, and an auditor
-- # looking for the policy a driver signed for will expect to find it.
-- ################################################################################################

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype, authority,
                             citation, applieswhen, evidencekind, evidencesource, origin,
                             extendable, reviewrequired, determination, blocking, gate, grouping,
                             duestage, duetext, recurrence, warndays, note, sortorder, effectivefrom)
VALUES (UUID(), 'company', 'WORKPLACE_POLICY', 'Company work policy',
        'The company''s own workplace policy - the rules of employment every driver is given and '
        'signs for. TripProof does not say what belongs in it; it keeps the current one on file so '
        'that what a driver signed for can be produced.',
        'policy', 'Company policy', NULL, NULL,
        'document', 'credential:WORKPLACE_POLICY', 'office', 0, 0, 0, 1, 'deficiency', 'company',
        'ongoing', NULL, 'once', 30, NULL, 45, CURRENT_DATE);
