-- ################################################################################################
-- # 133 - authorization, with a z.
-- #
-- # 15 U.S.C. 1681b(b) is a US statute and the form a driver signs is a US form. The engine's own
-- # prose can read however it reads; what a requirement is CALLED is what the office and an auditor
-- # see beside the citation, and it should match the document.
-- ################################################################################################

UPDATE compliancerules
   SET name = REPLACE(name, 'authorisation', 'authorization')
 WHERE name LIKE '%authorisation%';
