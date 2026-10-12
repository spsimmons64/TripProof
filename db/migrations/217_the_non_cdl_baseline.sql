-- ################################################################################################
-- # 217 - what a NEMT operator asks of a non-CDL driver, offered rather than imposed.
-- #
-- # A non-CDL driver is reached by 13 of the 45 rules in the catalog, and that is correct: Part 382
-- # and 391 Subpart C are about commercial motor vehicles, and saying otherwise would make the
-- # citations false. But nobody runs NEMT on that basis. Brokers, payers and the companies
-- # themselves ask for a background check, a drug screen, defensive driving and a competency check
-- # on every driver, and until now each of those had to be invented by hand.
-- #
-- # OFFERED, NOT IMPOSED. These rules carry `offered = 1`, which means no regulation puts them in
-- # force: they sit on Company - Driver Qualifications switched off, and the company turns on the
-- # ones its contracts ask for. That is a different thing from a rule whose condition happens not
-- # to reach somebody, and the file says which it is.
-- #
-- # The authority line says contract, never regulation. A background check a broker asks for is not
-- # a federal requirement and must never print as one - the same reasoning 194 set out for why a
-- # driving record obtained on a Class E driver is not a 49 CFR 391.23 record.
-- #
-- # The drug screen gets its OWN evidence, `credential:DRUG_SCREEN`, and is deliberately not filed
-- # against `drugtest:preemployment`. A non-DOT positive is an employment matter; a DOT positive is
-- # a federal prohibition that goes to the Clearinghouse. Letting one satisfy the other would be
-- # the worst error in this application.
-- #
-- # NO INVENTED RENEWAL PERIODS. Each of these expires on the date the document itself carries, if
-- # it carries one. Where a contract wants a background check every year, that interval is the
-- # contract's and the company sets it on its own copy of the rule.
-- #
-- # NOT ADDED HERE: the annual driving record, the road test, the employment application and the
-- # previous-employer history. All four already exist and are already adoptable - a company that
-- # wants them on non-CDL drivers elects them on the same page. Writing second copies would give
-- # one obligation two rows and two answers.
-- ################################################################################################

ALTER TABLE compliancerules
  ADD COLUMN IF NOT EXISTS offered TINYINT(1) NOT NULL DEFAULT 0 AFTER extendnote;

INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype, authority,
                             citation, applieswhen, evidencekind, evidencesource, origin,
                             extendable, extendnote, offered, reviewrequired, determination,
                             blocking, gate, grouping, duestage, duetext, recurrence, warndays,
                             note, sortorder, effectivefrom)
SELECT UUID(), 'driver', t.code, t.name, t.description, 'contract', t.authority, NULL, NULL,
       'document', CONCAT('credential:', t.credential), 'office', 1,
       'Already a company requirement. Adopting it is how it reaches anybody at all.',
       1, 0, 0, 1, 'deficiency', 'company', t.duestage, NULL, 'ondocument', 30, NULL,
       t.sortorder, CURRENT_DATE
  FROM (
    SELECT 'NONDOT_DRUG_SCREEN' AS code,
           'Pre-employment drug screen (non-DOT)' AS name,
           'A drug screen the company or its broker asks for, outside the federal programme. It is '
           'kept apart from the DOT pre-employment test on purpose: a non-DOT positive is an '
           'employment matter for this company to decide, while a DOT positive is a federal '
           'prohibition reported to the Clearinghouse. One can never stand in for the other.'
             AS description,
           'Broker and payer contracts' AS authority, 'DRUG_SCREEN' AS credential,
           'prehire' AS duestage, 310 AS sortorder
    UNION ALL SELECT 'BACKGROUND_CHECK',
           'Criminal background check',
           'A criminal history check on the driver. Not a federal requirement for a non-CDL driver '
           'and not the same thing as the Florida Level 1 screening, which has its own rule and its '
           'own statute. The scope, the lookback and how often it is repeated are the contract''s '
           'to set.',
           'Broker and payer contracts', 'BACKGROUND_CHECK', 'prehire', 311
    UNION ALL SELECT 'SEX_OFFENDER_CHECK',
           'Sex offender registry check',
           'A search of the public sex offender registries. Commonly asked of anybody transporting '
           'passengers who are elderly, disabled or minors, and commonly asked again each year.',
           'Broker and payer contracts', 'SEX_OFFENDER_CHECK', 'prehire', 312
    UNION ALL SELECT 'ABUSE_REGISTRY_CHECK',
           'Abuse registry check',
           'A search of the State abuse, neglect and exploitation registries. Asked by many States '
           'and brokers of anybody working with vulnerable adults or children.',
           'Broker and payer contracts', 'ABUSE_REGISTRY_CHECK', 'prehire', 313
    UNION ALL SELECT 'DEFENSIVE_DRIVING',
           'Defensive driving course',
           'A recognised defensive driving course. Not required by any regulation reaching a '
           'non-CDL driver; asked for by insurers and brokers, and usually repeated every few '
           'years on an interval the contract or the insurer sets.',
           'Broker, payer and insurer requirements', 'DEFENSIVE_DRIVING', 'athire', 314
    UNION ALL SELECT 'FIRST_AID',
           'First aid certification',
           'A current first aid certificate. The card carries its own expiry, which is what '
           'TripProof tracks.',
           'Broker and payer contracts', 'FIRST_AID', 'athire', 315
    UNION ALL SELECT 'CPR',
           'CPR and AED certification',
           'A current CPR and AED certificate. The card carries its own expiry, which is what '
           'TripProof tracks.',
           'Broker and payer contracts', 'CPR', 'athire', 316
    UNION ALL SELECT 'ADA_PROFICIENCY',
           'Passenger assistance and equipment proficiency',
           'A demonstrated check that the driver can assist passengers and use the vehicle''s '
           'accessibility equipment safely. Where the fleet carries wheelchairs, 49 CFR 37.173 '
           'already requires training and has its own rule; this is the company''s own competency '
           'check, which goes further and reaches drivers the regulation does not.',
           'Company policy', 'ADA_PROFICIENCY', 'predrive', 317
  ) AS t
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules c
                    WHERE c.subject = 'driver' AND c.code = t.code AND c.effectiveto IS NULL);
