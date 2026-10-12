-- Payers have a fax.
--
-- Still the way a good deal of this business moves: prior authorisations, appeals and
-- records requests all go by fax at plenty of payers, and the number belongs with the
-- address rather than in somebody's notes. The company profile has carried one since the
-- beginning; this is the same field in the same place on the other side of the arrangement.

ALTER TABLE payers
  ADD COLUMN IF NOT EXISTS fax VARCHAR(32) NULL AFTER phone;
