-- ################################################################################################
-- # 222 - carrying Medicaid trips is not the same as billing Medicaid.
-- #
-- # 220 put the Medicaid enrolment and the NPI behind `company.medicaid` - "do you carry Medicaid
-- # funded trips?" - and made the enrolment a HARD STOP. Both are wrong, and the first is the real
-- # error.
-- #
-- # Most NEMT operators subcontract to a broker. They carry Medicaid passengers every day and never
-- # submit a Medicaid claim: the broker is the enrolled provider and the operator invoices the
-- # broker. Such a company needs no Medicaid enrolment of its own and no NPI, and telling it that
-- # a missing provider number stops the business is simply untrue.
-- #
-- # So a new question separates the two, and both rules move behind it. Where a company does bill
-- # directly the enrolment matters a great deal - unenrolled claims are not payable - but it is
-- # reported as a deficiency rather than as a stop, because it stops the INVOICING, not the
-- # driving, and this application is about whether a vehicle may go out.
-- #
-- # Until the new question is answered both read "cannot be decided", which is the honest state: a
-- # company that has not said how it is paid is not a company anybody can say this about.
-- ################################################################################################

INSERT INTO companyquestions (code, factname, question, help, sortorder) VALUES
 ('BILLS_DIRECT', 'company.billsdirect',
  'Do you bill Medicaid or another payer directly, rather than invoicing a broker?',
  'A company that subcontracts to a broker carries Medicaid passengers but submits no Medicaid '
  'claims - the broker is the enrolled provider. Only a company that bills a payer itself needs '
  'its own Medicaid enrolment and NPI.', 12)
ON DUPLICATE KEY UPDATE active = 1;

UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"company.medicaid","is":true},'
                     '{"fact":"company.billsdirect","is":true}]}',
       gate = 'deficiency',
       description = 'A provider that bills a State Medicaid programme must be enrolled with it, '
                     'and the enrolment screened and revalidated on the State''s schedule. Claims '
                     'submitted while unenrolled are not payable. A company paid by a broker does '
                     'not need its own enrolment - the broker is the enrolled provider.'
 WHERE subject = 'company' AND code = 'MEDICAID_ENROLLMENT' AND effectiveto IS NULL;

UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"company.medicaid","is":true},'
                     '{"fact":"company.billsdirect","is":true}]}',
       description = 'The National Provider Identifier a provider bills under. Needed by a company '
                     'that submits its own claims; a company invoicing a broker bills under the '
                     'broker''s arrangements and needs none.'
 WHERE subject = 'company' AND code = 'NPI_REGISTRATION' AND effectiveto IS NULL;
