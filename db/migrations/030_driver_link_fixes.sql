-- ################################################################################################
-- # 030 - point the two driver rows without a verifiable link at sources that answer.
-- #
-- # www.fmcsa.dot.gov refuses scripted requests (403), so its pages cannot be checked by
-- # db/tools/verify_citations.py or the link check. PSP now links to its statutory authority at the
-- # Office of the Law Revision Counsel, and CDLIS to AAMVA, which runs it; both return 200. The
-- # portals themselves (psp.fmcsa.dot.gov, fmcsa.dot.gov) are named in the notes instead.
-- ################################################################################################
UPDATE compliancedocs SET
    sourceurl = 'https://uscode.house.gov/view.xhtml?req=granuleid:USC-prefix-title49-section31106&num=0&edition=prelim',
    description = 'Five years of crashes and three years of roadside inspections from MCMIS, ordered through the PSP portal at psp.fmcsa.dot.gov. Voluntary, and it needs the driver''s written consent under the FCRA.'
    WHERE jurisdiction = 'US' AND code = 'PSP_REPORT';

UPDATE compliancedocs SET
    sourceurl = 'https://www.aamva.org/technology/systems/commercial-driver-systems/commercial-driver-license-information-system'
    WHERE jurisdiction = 'US' AND code = 'CDLIS_CHECK';
