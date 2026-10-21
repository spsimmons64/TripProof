-- The supervisor is told on screen.
--
-- Appointing somebody sent them an email asking them to sign their training record. It is not
-- needed: they already have a login here, and the banner on their dashboard says the same
-- thing the moment they sign in - driven by the appointment itself, so it appears without
-- anything being sent and stays until they have signed.
--
-- An email that duplicates a banner is one more thing to deliver, to land in a spam folder,
-- and to be wrong about - 281 added this column so it was only ever sent once, and with
-- nothing sending it the column records nothing.

ALTER TABLE companyroles DROP COLUMN IF EXISTS notifiedon;
