-- Every driver must hold a valid licence for the vehicle they operate. Including this company's.
--
-- 49 CFR 391.11(b)(5). DRIVER_LICENCE asks that question and was gated
-- {"not":{"fact":"company.medicaid","is":true}} - so it was switched OFF for any company that
-- carries Medicaid trips, which is every company this product is sold to.
--
-- What stood in its place for those companies is DRIVER_LICENSE_COPY, which asks a different
-- question: 42 U.S.C. 1396a(a)(87)(B) requires the licence to be COPIED INTO THE FILE. Keeping a
-- photocopy and holding a valid licence are not the same obligation, and swapping one for the
-- other meant nobody was asking the first.
--
-- The result, reproduced against the live account before this was written: a driver assigned
-- Class B heavy CDL work passed with a Class E operator licence, passed with the licence marked
-- not active, and passed with no licence on file at all. Zero failing requirements in all three
-- states, because the evidence reader returned the literal 'qualified' whatever it found and the
-- only rule that would have compared anything was turned off.
--
-- Both now apply. They do not duplicate each other:
--
--   DRIVER_LICENCE       does this driver hold a currently valid licence of a class that covers
--                        the work - 49 CFR 391.11(b)(5), 49 CFR 383.91
--   DRIVER_LICENSE_COPY  is a copy of it in the file - 42 U.S.C. 1396a(a)(87)(B)
--
-- app/rules.py now makes the comparison (_licence_verdict), and `licence` is answered on the
-- Licenses Held screen that DRIVER_LICENSE_COPY already uses - it had no screen before, so even
-- where the rule did apply it could not be cleared.

UPDATE compliancerules
   SET applieswhen = NULL,
       note = NULL
 WHERE code = 'DRIVER_LICENCE';

-- Say which of the two it is, on the row an auditor reads. "Driver's Licenses" beside "Valid
-- driver's license" is two names for what looks like one thing.
UPDATE compliancerules
   SET name = 'Copy of the driver''s license in the file'
 WHERE code = 'DRIVER_LICENSE_COPY';
