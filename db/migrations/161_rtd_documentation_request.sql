-- ################################################################################################
-- # 161 - something to ask the driver for.
-- #
-- # A driver who disclosed a prior pre-employment violation owes proof that the return-to-duty
-- # process was completed, and that proof is held by them, not by this company - the SAP who
-- # evaluated them worked for somebody else, and 49 CFR 40.25(e) asks the employer to obtain
-- # information establishing compliance before using the person.
-- #
-- # So the office needs to be able to ask for it down a link, the same way it asks for a medical
-- # card. That takes a credential type, because that is what the asking is built on.
-- ################################################################################################

INSERT INTO credentialtypes (recordid, code, name, subject, category, description)
SELECT UUID(), 'RTD_DOCUMENTATION', 'Return-to-duty documentation', 'driver', 'compliance',
       'Proof that a previously disclosed DOT drug or alcohol violation was resolved through the '
       'return-to-duty process - the SAP determination, the return-to-duty test result, or both.'
 WHERE NOT EXISTS (SELECT 1 FROM credentialtypes WHERE code = 'RTD_DOCUMENTATION');
