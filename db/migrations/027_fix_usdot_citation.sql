-- ################################################################################################
-- # 027 - correct the USDOT registration row.
-- #
-- # 022 cited 49 CFR 390.19, which today covers motor carrier identification reports for certain
-- # Mexico-domiciled carriers only. The general duty is in the Unified Registration System:
-- # 49 CFR 390.201(b) says who must file Form MCSA-1, and 390.201(d) sets the every-24-months
-- # update schedule by the last digit of the USDOT number. Form MCSA-1 replaced the MCS-150, so the
-- # row is renamed with it; 49 CFR 390.21 (displaying the number on the vehicle) moves into the note
-- # where it belongs, since it is not a document.
-- ################################################################################################
UPDATE compliancedocs SET
    code = 'USDOT_REGISTRATION',
    name = 'USDOT registration and biennial update (Form MCSA-1)',
    renewal = 'Every 24 months, in the month set by the last digit of the USDOT number',
    description = 'Registration with FMCSA through the Unified Registration System, kept current by the biennial update. The number must also be displayed on each self-propelled commercial vehicle (49 CFR 390.21). A purely intrastate operation needs no federal number, though many States require their own USDOT registration.',
    legalcitation = '49 CFR 390.201(b), (d)',
    sourceurl = 'https://www.ecfr.gov/current/title-49/section-390.201',
    updated = UTC_TIMESTAMP()
    WHERE jurisdiction = 'US' AND code = 'USDOT_MCS150';

-- The govinfo /link/uscode/ redirector answers 502 intermittently; point U.S. Code rows at the
-- Office of the Law Revision Counsel, which serves the official text directly.
UPDATE compliancedocs SET
    sourceurl = 'https://uscode.house.gov/view.xhtml?req=granuleid:USC-prefix-title42-section1396a&num=0&edition=prelim'
    WHERE sourceurl = 'https://www.govinfo.gov/link/uscode/42/1396a';

UPDATE compliancedocs SET
    sourceurl = 'https://uscode.house.gov/view.xhtml?req=granuleid:USC-prefix-title15-section1681b&num=0&edition=prelim'
    WHERE sourceurl = 'https://www.govinfo.gov/link/uscode/15/1681b';
