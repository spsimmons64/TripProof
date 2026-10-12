-- ################################################################################################
-- # 024 - separate "required of everyone" from "required if".
-- #
-- # obligation  'required'     every NEMT company that bills Medicaid and handles PHI needs it
-- #             'conditional'  the law requires it only when appliesif is true (fleet, interstate
-- #                            operation, CDL drivers, headcount, exposure, federal awards)
-- #             'recommended'  not law: brokers, insurers or good practice
-- #
-- # The conditions that are simply true of the business (bills Medicaid, handles PHI) stay in
-- # appliesif as context, but don't make a document conditional.
-- ################################################################################################
ALTER TABLE compliancedocs DROP CONSTRAINT IF EXISTS ck_compliancedocs_obligation;
ALTER TABLE compliancedocs
    ADD CONSTRAINT IF NOT EXISTS ck_compliancedocs_obligation
        CHECK (obligation IN ('required', 'conditional', 'recommended'));

UPDATE compliancedocs SET obligation = 'conditional'
    WHERE jurisdiction = 'US' AND code IN (
        'USDOT_MCS150',          -- interstate, and over 10,000 lb GVWR or more than 8 passengers for compensation
        'DA_TESTING_PROGRAM',    -- CDL drivers in commercial motor vehicles
        'CLEARINGHOUSE',         -- CDL drivers in commercial motor vehicles
        'BBP_PLAN',              -- staff with occupational exposure to blood or OPIM
        'OSHA_300',              -- more than 10 employees, outside the partially exempt industries
        'SAM_REGISTRATION',      -- only to hold federal contracts or grants
        'DA_POLICY_RECEIPT',     -- driver file: CDL drivers
        'CLEARINGHOUSE_CONSENT', -- driver file: CDL drivers
        'FCRA_FORMS');           -- driver file: background checks through a consumer reporting agency

UPDATE compliancedocs SET appliesif = 'Seeks federal contracts or grants; useful for exclusion screening either way'
    WHERE jurisdiction = 'US' AND code = 'SAM_REGISTRATION';
