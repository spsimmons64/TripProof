-- ################################################################################################
-- # 220 - the registrations a NEMT operator holds, and twelve credential types nothing asks for.
-- #
-- # SIX REGISTRATIONS. Each has had a credential type since early on with no rule pointing at it,
-- # so a company could be unenrolled with its State Medicaid programme, hold no NPI and have let
-- # its local tax receipt lapse, and nothing said so. Conditioned on what the company has already
-- # told us rather than asked again: Medicaid enrolment and the NPI follow the Medicaid answer,
-- # SAM.gov follows the SAM.gov answer, the certificate of public convenience is Florida's, and
-- # the HIPAA risk analysis follows the HIPAA answer.
-- #
-- # TWELVE DEAD CREDENTIAL TYPES. Each was superseded by a table of its own - `drivermvrs`,
-- # `annualreviews`, `roadtests`, `driverreports`, `exclusionchecks`, `transitmedicals`,
-- # `driverlicenses`, `documentsignatures` - and no rule has pointed at any of them for a long
-- # time. Leaving them active invites somebody to file a document against a requirement it cannot
-- # answer, which is worse than having nowhere to put it. Retired, not dropped: anything already
-- # filed keeps its record.
-- ################################################################################################

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype, authority,
                             citation, applieswhen, evidencekind, evidencesource, origin,
                             extendable, reviewrequired, determination, blocking, gate, grouping,
                             duestage, duetext, recurrence, warndays, note, sortorder,
                             effectivefrom)
SELECT UUID(), 'company', t.code, t.name, t.description, t.authoritytype, t.authority, t.citation,
       t.applieswhen, 'document', CONCAT('credential:', t.credential), 'office', 1, 0, 0, 1,
       t.gate, t.grouping, 'ongoing', NULL, 'ondocument', 30, NULL, t.sortorder, CURRENT_DATE
  FROM (
    SELECT 'MEDICAID_ENROLLMENT' AS code, 'State Medicaid enrollment' AS name,
           'A provider must be enrolled with the State Medicaid programme it bills, and the '
           'enrolment screened and revalidated on the State''s schedule. Billing while unenrolled '
           'is not a paperwork problem - the claims are not payable.' AS description,
           'regulation' AS authoritytype, 'CMS and State Medicaid agency' AS authority,
           '42 CFR 455 Subpart E; 42 CFR 424.516' AS citation,
           '{"fact":"company.medicaid","is":true}' AS applieswhen,
           'MEDICAID_ENROLLMENT' AS credential, 'hardstop' AS gate,
           'regulatory' AS grouping, 61 AS sortorder
    UNION ALL SELECT 'NPI_REGISTRATION', 'National Provider Identifier',
           'The NPI a health care provider bills under. Required on Medicaid and Medicare claims '
           'and asked for by every broker that credentials a transportation provider.',
           'regulation', 'CMS', '45 CFR 162.406', '{"fact":"company.medicaid","is":true}',
           'NPI_REGISTRATION', 'deficiency', 'regulatory', 62
    UNION ALL SELECT 'SAM_REGISTRATION', 'SAM.gov entity registration',
           'Registration in the System for Award Management, kept current. Where a contract, grant '
           'or programme requires SAM.gov screening it usually requires the entity to be '
           'registered there as well.',
           'contract', 'Federal contracting requirement', '2 CFR 25.200',
           '{"fact":"company.samgov","is":true}', 'SAM_REGISTRATION', 'deficiency', 'regulatory', 63
    UNION ALL SELECT 'BUSINESS_LICENSE', 'Local business tax receipt',
           'The county or municipal licence to trade. Not a transportation requirement, and the '
           'first thing a broker asks for when it credentials a new provider.',
           'regulation', 'County or municipality', 'Local ordinance', NULL,
           'BUSINESS_LICENSE', 'deficiency', 'company', 64
    UNION ALL SELECT 'COPEC', 'Certificate of Public Convenience and Necessity',
           'Several Florida counties require a certificate before a vehicle may carry passengers '
           'for hire within them. It is a county instrument, so which counties and on what terms '
           'is a local question.',
           'regulation', 'County', 'County ordinance',
           '{"fact":"company.state","eq":"FL"}', 'COPEC', 'deficiency', 'company', 65
    UNION ALL SELECT 'HIPAA_RISK_ANALYSIS', 'HIPAA security risk analysis',
           'An accurate and thorough assessment of the risks to electronic protected health '
           'information, with the measures taken to reduce them. Required of a covered entity and '
           'of a business associate, and the first document asked for in a breach investigation.',
           'regulation', 'HHS', '45 CFR 164.308(a)(1)(ii)(A)',
           '{"fact":"company.hipaa","is":true}', 'HIPAA_RISK_ANALYSIS', 'deficiency', 'regulatory',
           66
  ) AS t
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules c
                    WHERE c.subject = 'company' AND c.code = t.code AND c.effectiveto IS NULL);

-- Superseded by tables of their own. Nothing points at them and nothing should.
UPDATE credentialtypes SET active = 0
 WHERE subject = 'driver'
   AND code IN ('MVR', 'ROAD_TEST', 'ANNUAL_REVIEW', 'PSP_REPORT', 'CDLIS_REPORT',
                'SAFETY_PERFORMANCE', 'TRANSIT_MEDICAL', 'DRIVER_LICENSE', 'OIG_EXCLUSION',
                'PREEMP_DA_QUESTIONNAIRE', 'RTD_DOCUMENTATION', 'CDL_PASSENGER');

-- The policies became published templates in 207 and 210, and the FCRA consent is a signature on
-- the driver's own file. None of the three is a document the company uploads any more.
UPDATE credentialtypes SET active = 0
 WHERE subject = 'company' AND code IN ('DRUG_ALCOHOL_POLICY', 'WORKPLACE_POLICY', 'FCRA_CONSENT');
