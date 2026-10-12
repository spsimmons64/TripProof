-- ################################################################################################
-- # 026 - the catalog is for the transportation PROVIDER the broker hires, not for the broker.
-- #
-- # Under a broker model the broker holds the Medicaid provider agreement: it enrolls, bills, gets
-- # the NPI, discloses ownership and answers for the provider-agreement record rules. The company
-- # driving the trips only carries those duties when it enrolls with Medicaid in its own name, so
-- # they move from "required" to "required if", with the condition spelled out.
-- #
-- # What stays required for a subcontracted provider: exclusion screening (no federal health care
-- # program money may pay an excluded person, subcontractor or not), the two written processes the
-- # 2021 statute puts on any provider of nonemergency transportation, the EIN, and HIPAA - a
-- # subcontracted provider is normally a business associate of the broker or plan.
-- # The notice of privacy practices is a covered entity's duty, so it leaves the policies row.
-- ################################################################################################
UPDATE compliancedocs SET obligation = 'conditional',
    appliesif = 'Enrolls and bills Medicaid in its own name (under a broker, the broker bills)'
    WHERE jurisdiction = 'US' AND subject = 'company' AND code = 'NPI';

UPDATE compliancedocs SET obligation = 'conditional',
    appliesif = 'Enrolled with the State Medicaid agency in its own name; some States also enroll broker-network providers',
    description = 'Screened and enrolled with the State Medicaid agency. A company that only subcontracts to a broker is credentialed by that broker instead, unless the State enrolls network providers.'
    WHERE jurisdiction = 'US' AND subject = 'company' AND code = 'MEDICAID_ENROLLMENT';

UPDATE compliancedocs SET obligation = 'conditional',
    appliesif = 'Holds a Medicaid provider agreement in its own name'
    WHERE jurisdiction = 'US' AND subject = 'company' AND code = 'OWNERSHIP_DISCLOSURE';

UPDATE compliancedocs SET obligation = 'conditional',
    appliesif = 'Holds a Medicaid provider agreement in its own name',
    description = 'Keep records that fully disclose the services billed and furnish them to the State and HHS on request. A subcontracted provider keeps trip records under its broker contract instead.'
    WHERE jurisdiction = 'US' AND subject = 'company' AND code = 'RECORD_RETENTION';

UPDATE compliancedocs SET
    appliesif = 'Paid with Federal health care program money, directly or as a subcontractor'
    WHERE jurisdiction = 'US' AND subject = 'company' AND code = 'EXCLUSION_SCREENING';

UPDATE compliancedocs SET
    name = 'HIPAA privacy and security policies',
    appliesif = 'Handles protected health information, as a covered entity or a business associate',
    description = 'Written policies and procedures, kept for 6 years. A covered entity also issues a notice of privacy practices (45 CFR 164.520); a subcontracted provider usually acts as a business associate and does not.',
    legalcitation = '45 CFR 164.316'
    WHERE jurisdiction = 'US' AND subject = 'company' AND code = 'HIPAA_POLICIES';

UPDATE compliancedocs SET obligation = 'conditional',
    appliesif = 'Enrolled with AHCA as a Florida Medicaid provider in its own name',
    description = 'Screening of the provider and each principal - officers, directors, billing agents, managing employees and anyone holding 5% or more. A broker''s subcontractor is screened under the broker''s contract instead.'
    WHERE jurisdiction = 'FL' AND subject = 'company' AND code = 'FL_L2_SCREENING';

UPDATE compliancedocs SET obligation = 'conditional',
    appliesif = 'Holds a Florida Medicaid provider agreement in its own name'
    WHERE jurisdiction = 'FL' AND subject = 'company' AND code = 'FL_MEDICAID_RECORDS';
