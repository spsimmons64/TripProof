-- ################################################################################################
-- # 223 - the certificate of public convenience is a county's question, not Florida's.
-- #
-- # 220 conditioned it on `company.state = 'FL'`, so every Florida operator was asked for one. A
-- # COPEC is a COUNTY instrument: some counties require a certificate before a vehicle may carry
-- # passengers for hire within them, most do not, and each that does sets its own terms. Asking
-- # every Florida company for a document most of them have no way of obtaining is the same fault
-- # the county vehicle permit was deliberately left out to avoid - and I walked into it here.
-- #
-- # So it moves behind a question, like every other conditional thing in this catalog. A company
-- # that has not answered reads "cannot be decided", which is true: nobody can say whether a
-- # certificate is needed without knowing which counties the vehicles work in.
-- ################################################################################################

INSERT INTO companyquestions (code, factname, question, help, sortorder) VALUES
 ('COPEC_REQUIRED', 'company.copec',
  'Does a county you operate in require a Certificate of Public Convenience and Necessity?',
  'Some Florida counties require a certificate before a vehicle may carry passengers for hire '
  'within them. Most do not. Ask the county, or the Community Transportation Coordinator for it.',
  70)
ON DUPLICATE KEY UPDATE active = 1;

UPDATE compliancerules
   SET applieswhen = '{"fact":"company.copec","is":true}',
       description = 'Some counties require a certificate before a vehicle may carry passengers '
                     'for hire within them. It is a county instrument, so which counties and on '
                     'what terms is a local question - ask the county, or the Community '
                     'Transportation Coordinator for it.'
 WHERE subject = 'company' AND code = 'COPEC' AND effectiveto IS NULL;
