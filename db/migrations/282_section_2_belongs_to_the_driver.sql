-- Section 2 belongs to the driver.
--
-- An I-9 carries two signatures: the employee signs Section 1, and somebody from the office
-- certifies Section 2 after examining their documents. The second was filed as
-- `ownertype = 'user'` against the DRIVER's id - meaning "a user signed this", which is not
-- what those columns say. They say whose document it is, and an I-9 is the driver's.
--
-- Consequences while it stood: the signature belonged to nobody - it matched no user and was
-- excluded from the driver's own file - and anything counting what a user had signed
-- mis-attributed it.
--
-- Fixed by filing it where it belongs, under a doctype of its own. Both signatures now sit
-- on the driver, and they stay distinguishable: `signatures.signed()` keys by doctype, so
-- two rows called I9 would have collapsed into one and "has Section 1 been signed" could
-- have been answered by Section 2.

UPDATE documentsignatures
   SET ownertype = 'driver', doctype = 'I9_SECTION2'
 WHERE doctype = 'I9' AND ownertype = 'user';
