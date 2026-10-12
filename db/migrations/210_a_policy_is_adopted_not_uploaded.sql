-- ################################################################################################
-- # 210 - a published policy is answered by adopting it, and each one is adopted on its own day.
-- #
-- # Two faults, and the second is mine from 209.
-- #
-- # THE SSPP COULD NOT BE ANSWERED AT ALL. Its requirement reads `credential:SSPP` - a document the
-- # company uploads - and 209 retired `credentialtypes.SSPP` when the plan became a published
-- # template. So the plan is on the screen, fills itself in, prints, and the requirement goes on
-- # saying "Nothing on file yet" with nothing anywhere that could change it. The same trap is one
-- # step behind the other three: they only read green because a document was uploaded before they
-- # became templates.
-- #
-- # ONE DATE WAS STANDING FOR FOUR ADOPTIONS. `accounts.dapolicyeffective` is named for the drug
-- # and alcohol policy and was the only effective date there was, so the workplace policy, the PHI
-- # policy and the plan all printed it. Four documents adopted on four different days cannot share
-- # one field, and a plan that prints the day the D&A policy took effect is saying something nobody
-- # said.
-- #
-- # So adoption moves to `companypolicies`, which already exists per (account, policy) because a
-- # company may edit its own wording. A row there now means one of two things, or both: this
-- # company adopted this policy on this day, and/or these are its own words. Text becomes nullable
-- # because adopting the published wording is not editing it.
-- #
-- # What adoption IS: an effective date the company set. Not the template existing - that is true
-- # for everybody from the first day and is no act of theirs. A policy with no effective date
-- # prints "Effective Date: __________", which is not a policy anybody adopted.
-- ################################################################################################

ALTER TABLE companypolicies
  MODIFY COLUMN text LONGTEXT NULL,
  ADD COLUMN IF NOT EXISTS effectiveon DATE        NULL AFTER code,
  ADD COLUMN IF NOT EXISTS adoptedby   VARCHAR(36) NULL AFTER effectiveon,
  ADD COLUMN IF NOT EXISTS adoptedon   DATETIME    NULL AFTER adoptedby;

-- The date already given belongs to the policy it was given for. It is NOT copied to the other
-- three: nobody said when those took effect, and filling the blank with a guess is the fault this
-- migration exists to remove.
INSERT INTO companypolicies (accountid, code, effectiveon, adoptedon, text)
SELECT recordid, 'DRUG_POLICY', dapolicyeffective, UTC_TIMESTAMP(), NULL
  FROM accounts WHERE dapolicyeffective IS NOT NULL
ON DUPLICATE KEY UPDATE effectiveon = VALUES(effectiveon),
                        adoptedon   = COALESCE(companypolicies.adoptedon, VALUES(adoptedon));

-- The four rules now read the adoption. `policy:` falls back to a document of the same code where
-- one was filed before these became templates, so a company that uploaded its workplace policy in
-- September does not lose it.
UPDATE compliancerules SET evidencekind = 'policy', evidencesource = 'policy:DRUG_POLICY'
 WHERE subject = 'company' AND code = 'DRUG_ALCOHOL_POLICY' AND effectiveto IS NULL;
UPDATE compliancerules SET evidencekind = 'policy', evidencesource = 'policy:WORKPLACE_POLICY'
 WHERE subject = 'company' AND code = 'WORKPLACE_POLICY' AND effectiveto IS NULL;
UPDATE compliancerules SET evidencekind = 'policy', evidencesource = 'policy:PHI_POLICY'
 WHERE subject = 'company' AND code = 'PHI_POLICY' AND effectiveto IS NULL;
UPDATE compliancerules SET evidencekind = 'policy', evidencesource = 'policy:SSPP'
 WHERE subject = 'company' AND code = 'SSPP' AND effectiveto IS NULL;

-- What they ask for, in the words of what now answers them.
UPDATE compliancerules
   SET duetext = 'Adopted with an effective date'
 WHERE subject = 'company' AND effectiveto IS NULL
   AND code IN ('DRUG_ALCOHOL_POLICY', 'WORKPLACE_POLICY', 'PHI_POLICY');

UPDATE compliancerules
   SET duetext = 'Adopted with an effective date, certified annually'
 WHERE subject = 'company' AND code = 'SSPP' AND effectiveto IS NULL;
