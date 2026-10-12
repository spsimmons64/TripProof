-- ################################################################################################
-- # 045 - the company's own email addresses.
-- #
-- # A customer is reached in three different ways and often at three different mailboxes: general
-- # correspondence, the desk that helps drivers and passengers, and whoever pays the bills. The
-- # account's users have their own addresses; these belong to the company.
-- ################################################################################################
ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS email        VARCHAR(128) NULL AFTER fax,
    ADD COLUMN IF NOT EXISTS supportemail VARCHAR(128) NULL AFTER email,
    ADD COLUMN IF NOT EXISTS billingemail VARCHAR(128) NULL AFTER supportemail;
