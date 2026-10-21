-- A supervisor is told when they can act on it.
--
-- Appointing somebody emailed them straight away: "you hold this, and your training record
-- is waiting for your signature". For an existing user that is right. For one who was
-- invited five minutes ago it is not - they cannot sign anything until they have set a
-- password and signed in, so the mail arrives before the thing it asks for exists, and the
-- link in it lands on a login screen.
--
-- So the telling is held until they can act: at appointment if they already sign in here,
-- and otherwise at their first login. This column is what stops it being told twice - the
-- date it was sent, on the appointment itself rather than on the person, because somebody
-- appointed, resigned and appointed again is owed the mail a second time.

ALTER TABLE companyroles
  ADD COLUMN IF NOT EXISTS notifiedon DATETIME NULL;
