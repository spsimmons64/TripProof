-- ################################################################################################
-- # 378 - a payer's return procedure and confirmation notes, dropped.
-- #
-- # Typed on the payer and read back nowhere. The broker's reference is taken where it is needed,
-- # on Broker Confirmed.
-- ################################################################################################

ALTER TABLE accountpayers DROP COLUMN IF EXISTS returnprocedure;
ALTER TABLE accountpayers DROP COLUMN IF EXISTS confirmationneeded;
