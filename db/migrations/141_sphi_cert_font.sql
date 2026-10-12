-- ################################################################################################
-- # 141 - the hand the previous employer signs in.
-- #
-- # They sign the way everybody else here signs: they type their name and pick a hand to draw it in.
-- # What is different is that nobody proves who they are first - there is nothing to prove against,
-- # since a previous employer has no record in this system - so the typed name draws the signature
-- # on that one page and is kept nowhere else as a signature of record.
-- ################################################################################################

ALTER TABLE employerinquiries
    ADD COLUMN IF NOT EXISTS certfontkey VARCHAR(24) NULL AFTER certsignature;
