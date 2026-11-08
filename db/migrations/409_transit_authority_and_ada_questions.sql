-- ################################################################################################
-- # 409 - two Operations questions the federal and Medicaid requirements turn on.
-- #
-- # PUBLIC_TRANSIT  42 U.S.C. 1396a(a)(87) excludes public transit authorities from the federal
-- #                 Medicaid NEMT safeguards. Without the answer those rules cannot say whether they
-- #                 reach the company at all.
-- # DEMAND_RESPONSE The ADA transportation rules in 49 CFR Part 37 reach an entity that operates a
-- #                 demand responsive system, public or private (37.173 names it in so many words).
-- ################################################################################################

INSERT INTO companyquestions (code, factname, question, help, sortorder, active)
SELECT 'PUBLIC_TRANSIT', 'company.public_transit_authority',
       'Is your company a public transit authority - a city, county or regional transit agency?',
       'The federal Medicaid NEMT safeguards - exclusion screening, a valid driver''s license, and the drug-law and driving-history processes - do not apply to a public transit authority. 42 U.S.C. 1396a(a)(87).',
       11, 1
WHERE NOT EXISTS (SELECT 1 FROM companyquestions WHERE code = 'PUBLIC_TRANSIT');

INSERT INTO companyquestions (code, factname, question, help, sortorder, active)
SELECT 'DEMAND_RESPONSE', 'operation.ada_part37_covered',
       'Do you operate a demand-response service - rides scheduled on request rather than fixed routes?',
       'Turns on the federal ADA transportation rules for a company that operates a demand-response service, public or private: drivers trained to proficiency, working lifts and securement, and help with boarding. 49 CFR 37.161, 37.165 and 37.173.',
       6, 1
WHERE NOT EXISTS (SELECT 1 FROM companyquestions WHERE code = 'DEMAND_RESPONSE');
