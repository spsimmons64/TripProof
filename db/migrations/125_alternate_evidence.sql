-- ################################################################################################
-- # 125 - two requirements, sometimes one examination.
-- #
-- # 49 CFR 391.43 and F.A.C. 14-90.0041 are separate requirements with separate authorities,
-- # standards and triggers, and neither is a special case of the other:
-- #
-- #                    FEDERAL 391.43                 FLORIDA 14-90.0041
-- #   applies when     federal qualification          the transit system is covered
-- #   standard         FMCSA medical standards        FDOT bus transit standards
-- #   evidence         Medical Examiner's Certificate FDOT 725-030-11 or permitted equivalent
-- #   return to duty   no equivalent rule             after 30+ days off ill or injured
-- #
-- # So they stay two rules. What they are NOT is two examinations by definition: 14-90.0041 lets a
-- # bus transit system adopt medical standards other than the form's, provided those standards meet
-- # or exceed the FDOT requirements, and keep that standard's certificate or an appropriate medical
-- # examiner's letter in place of the FDOT certificate. Where a system has done that, one physical
-- # can answer both, and sending the driver for a second one is cost with no compliance in it.
-- #
-- # That is a condition, not a default, so it is a question the company answers rather than an
-- # assumption the software makes. Until it is answered the Florida rule asks for its own evidence.
-- #
-- #   rule ---- evidencesource ------> what it normally reads
-- #        \
-- #         `-- alternatesource -----> what may answer it instead
-- #             alternatewhen -------> only while this is true
-- #
-- # The evidence is not copied either way. `complianceevidence` already says one record can answer
-- # many rules; this says when the engine may work that out for itself instead of being told.
-- ################################################################################################

ALTER TABLE compliancerules
    ADD COLUMN IF NOT EXISTS alternatesource VARCHAR(64) NULL AFTER evidencesource,
    ADD COLUMN IF NOT EXISTS alternatewhen   JSON        NULL AFTER alternatesource;

INSERT INTO companyquestions (code, factname, question, help, sortorder) VALUES
  ('TRANSIT_MEDICAL_ALT', 'company.transitmedicalalt',
   'Have you adopted medical standards that meet or exceed the FDOT bus transit standards?',
   'F.A.C. 14-90.0041(1)(b) lets a covered system use its own medical qualification standards in place of FDOT Form 725-030-11, so long as they meet or exceed it, and keep that standard''s certificate or a medical examiner''s letter instead. Answer yes only if you have actually adopted such a standard: it lets one examination answer both the federal and the Florida requirement rather than sending the driver for two.',
   25)
ON DUPLICATE KEY UPDATE question = VALUES(question), help = VALUES(help), sortorder = VALUES(sortorder);

UPDATE compliancerules
   SET alternatesource = 'credential:DOT_MEDICAL_CARD',
       alternatewhen   = '{"fact":"company.transitmedicalalt","is":true}'
 WHERE code = 'FL_TRANSIT_MEDICAL' AND subject = 'driver';
