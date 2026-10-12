-- ################################################################################################
-- # 083 - an account user's own signature identity.
-- #
-- # A user signs company records the way a driver signs their application: the signature is created
-- # once, behind a date of birth and a Social Security number, and every later signing is that same
-- # hand proved the same way. A password says someone is at the keyboard with a login; it does not
-- # say who they are, and a signature has to.
-- #
-- # The number itself is never kept - only the same salted hash the drivers' is kept as, so the
-- # pair can be checked and nothing can be read back out of it.
-- ################################################################################################
ALTER TABLE users
    ADD COLUMN dob     DATE      NULL AFTER name,
    ADD COLUMN ssnhash CHAR(64)  NULL AFTER dob;

CREATE INDEX ix_users_ssnhash ON users (accountid, ssnhash);
