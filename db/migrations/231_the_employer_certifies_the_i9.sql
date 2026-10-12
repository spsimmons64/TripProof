-- The employer's half of the I-9.
--
-- Section 1 is the employee's statement and the driver signs it down a link. Section 2 is the
-- employer's certification - 8 CFR 274a.2(b)(1)(ii) - and it is a separate act by a separate
-- person, made after they have looked at the documents. Reading the form and certifying it are
-- the same moment in practice, but they are not the same fact, so reviewedon does not stand in
-- for this: a form can be read by somebody with no authority to attest to anything.
--
-- The signature is the certifying user's own, created once behind their date of birth and Social
-- Security number, exactly as the annual review is signed. It is kept here by its id so the form
-- on file and the signature behind it cannot drift apart.

ALTER TABLE signingrequests
  ADD COLUMN certifiedon DATETIME NULL AFTER reviewedby,
  ADD COLUMN certifiedby CHAR(36) NULL AFTER certifiedon,
  ADD COLUMN certificationsigid CHAR(36) NULL AFTER certifiedby,
  -- The copy as the employee signed it, before the employer wrote on it. The certified form
  -- supersedes it and is what documentid points at from then on, but the page the driver actually
  -- put their hand to is not thrown away.
  ADD COLUMN employeedocumentid CHAR(36) NULL AFTER certificationsigid;
