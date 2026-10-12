-- ################################################################################################
-- # 195 - a company's own requirements.
-- #
-- # 194 let a company adopt one of OUR rules beyond its regulatory reach. This is the other half:
-- # requirements that are theirs entirely - a uniform policy, a defensive driving course, a form a
-- # broker insists on that nobody else has ever heard of. Every operator has a few, and until now
-- # the only place to put them was somebody's memory.
-- #
-- # They live in the same table as everything else, with an accountid. That is the whole design:
-- # the engine reads one catalog, so a company requirement gets the stages, the gates, the expiry
-- # arithmetic, the review rule, the dashboard, the validity panel and the disqualification banner
-- # without a line of code written for it. A separate table would have meant a second engine.
-- #
-- #   accountid NULL  ours. The regulations, shared by every account, ours to maintain.
-- #   accountid set   theirs. Never shown to anybody else, and never touched by our migrations.
-- #
-- # Answered by a credential, because that is what gives it a document, an issue date, an expiry
-- # and a place in the validity panel for nothing. The credential type is created with the rule and
-- # carries a generated code, so two companies inventing the same name cannot collide.
-- ################################################################################################

ALTER TABLE compliancerules
  ADD COLUMN accountid VARCHAR(36) NULL AFTER recordid,
  -- A blank form the company hands out - their own acknowledgement, their own checklist. Optional:
  -- plenty of requirements are a certificate somebody else issues.
  ADD COLUMN templatedocumentid VARCHAR(36) NULL AFTER description,
  ADD KEY ix_compliancerules_account (accountid, subject);

ALTER TABLE credentialtypes
  ADD COLUMN accountid VARCHAR(36) NULL AFTER recordid,
  ADD KEY ix_credentialtypes_account (accountid);
