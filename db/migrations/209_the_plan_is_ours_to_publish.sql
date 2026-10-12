-- ################################################################################################
-- # 209 - the SSPP and the PHI acknowledgment become published policies, like the other two.
-- #
-- # 202 made the SSPP a credential and 206 did the same for the PHI acknowledgment, so the only way
-- # to answer either was to go and write the document and upload it. For the drug and alcohol
-- # policies that was already settled in 207 and 208: TripProof publishes the wording, the company
-- # edits it if it wants to, and the named people fill themselves in from their appointments. These
-- # two are the same kind of thing and now behave the same way.
-- #
-- # The SSPP brings a person with it. Chapter 14-90 wants the plan to say who administers it, and
-- # a plan that names somebody who left is worse than one that names nobody - the same reasoning
-- # that moved the DER out of the document in 207. So the Safety Manager is an appointment in
-- # `companyroles` and the plan prints whoever holds it, in section 5.2, section 29 and appendix A.
-- #
-- # `credentialtypes.SSPP` and `credentialtypes.PHI_POLICY` are retired rather than dropped: a
-- # company that already uploaded one keeps the record, and nothing new can be filed against a
-- # requirement that is now answered by the published policy.
-- ################################################################################################

UPDATE compliancerules
   SET description = 'Florida requires a covered bus operator to adopt a System Safety Program '
                     'Plan and to certify compliance with it annually. TripProof publishes the '
                     'plan and fills in the company, its address, its effective date and its '
                     'Safety Manager; edit any of it and the edited plan is the one that prints. '
                     'Two of the driver requirements - the driver selection and training records, '
                     'and the hours of service limits - are obligations this plan creates.'
 WHERE subject = 'company' AND code = 'SSPP' AND effectiveto IS NULL;

UPDATE compliancerules
   SET description = 'The statement each driver acknowledges, naming what counts as protected '
                     'information and what they may and may not do with it. TripProof publishes '
                     'the wording; edit it and the edited version is what a driver receives. Their '
                     'signature is recorded on their own file - this is what they signed, which is '
                     'what anybody asking "acknowledging what?" needs to see.'
 WHERE subject = 'company' AND code = 'PHI_POLICY' AND effectiveto IS NULL;

UPDATE credentialtypes SET active = 0 WHERE code IN ('SSPP', 'PHI_POLICY');

-- The Safety Manager, asked of the same companies the plan is asked of. A role somebody holds, so
-- it reads `companyroles` rather than anything filed - the shape 204 settled for the DER.
INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype, authority,
                             citation, applieswhen, evidencekind, evidencesource, origin,
                             extendable, reviewrequired, determination, blocking, gate, grouping,
                             duestage, duetext, recurrence, warndays, note, sortorder, effectivefrom)
SELECT UUID(), 'company', 'SAFETY_MANAGER', 'Safety Manager',
       'Somebody in this company administers the System Safety Program Plan: the person who '
       'reviews driver qualifications and training, monitors inspections and maintenance, '
       'investigates safety events and certifies annual compliance. Name them here and the plan '
       'prints them; there is nothing to upload.',
       'regulation', 'FDOT', 'F.A.C. 14-90.004',
       '{"all":[{"fact":"company.state","eq":"FL"},{"fact":"company.transit","is":true}]}',
       'person', 'companyrole:safety', 'office', 0, 0, 0, 1, 'hardstop', 'regulatory',
       'ongoing', NULL, 'once', 30, NULL, 49, CURRENT_DATE
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules
                    WHERE subject = 'company' AND code = 'SAFETY_MANAGER'
                      AND effectiveto IS NULL);
