-- ################################################################################################
-- # 042 - the FCRA driver consent is the company's own document, as the two policies are.
-- #
-- # An account files its consent on the Documents page; the online driver application shows the
-- # most recent copy on its own page and records the signature against that file's SHA-256. An
-- # account that has filed none falls back to the wording we ship.
-- ################################################################################################
INSERT IGNORE INTO credentialtypes (recordid, code, name, subject, category, description, active)
VALUES
('a1000042-0000-4000-8000-000000000001', 'FCRA_CONSENT', 'FCRA driver consent', 'company', 'policy',
 'The disclosure and authorization a driver signs before any consumer report is obtained. The most recent copy is what the online driver application shows.',
 1);
