-- ################################################################################################
-- # 040 - the two policies a driver signs for are the company's own, not ours.
-- #
-- # The drug and alcohol policy and the workplace policy become company credential types, so an
-- # account files them on the Documents page like any other company document. The online driver
-- # application then shows the most recent copy of each and records the signature against that
-- # file's SHA-256, so what the driver acknowledged is the file they were shown.
-- #
-- # An account that has filed neither still works: the application falls back to the wording we
-- # ship, and the signature names that version instead.
-- ################################################################################################
INSERT IGNORE INTO credentialtypes (recordid, code, name, subject, category, description, active)
VALUES
('a1000040-0000-4000-8000-000000000001', 'DRUG_ALCOHOL_POLICY', 'Drug and alcohol policy', 'company', 'policy',
 'The written policy drivers are given and sign for. The most recent copy is what the online driver application shows.',
 1),
('a1000040-0000-4000-8000-000000000002', 'WORKPLACE_POLICY', 'Workplace policy', 'company', 'policy',
 'The workplace rules drivers are given and sign for. The most recent copy is what the online driver application shows.',
 1);
