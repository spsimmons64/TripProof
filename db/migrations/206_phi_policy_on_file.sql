-- ################################################################################################
-- # 206 - the PHI acknowledgment the drivers sign, kept as a document.
-- #
-- # The driver side has existed for a while: each driver signs an acknowledgment and their file
-- # records that they did. What was never asked for is the document itself - the thing they signed.
-- # An acknowledgment on a driver's file that points at nothing is a signature without a statement,
-- # and the first question anybody asks about one is "acknowledging what?".
-- #
-- # Conditioned the same way the driver's is, so a company that is not covered is not asked.
-- ################################################################################################

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype, authority,
                             citation, applieswhen, evidencekind, evidencesource, origin,
                             extendable, reviewrequired, determination, blocking, gate, grouping,
                             duestage, duetext, recurrence, warndays, note, sortorder, effectivefrom)
VALUES (UUID(), 'company', 'PHI_POLICY',
        'Driver PHI confidentiality and privacy acknowledgment',
        'The document each driver signs, kept on file as the company''s copy. Their signature is '
        'recorded on their own file; this is the statement they signed, which is what anybody '
        'asking "acknowledging what?" needs to see.',
        'regulation', 'HHS', '45 CFR 164.530(b)',
        '{"fact":"company.hipaa","is":true}',
        'document', 'credential:PHI_POLICY', 'office', 0, 0, 0, 1, 'deficiency', 'regulatory',
        'ongoing', NULL, 'once', 30, NULL, 47, CURRENT_DATE);
