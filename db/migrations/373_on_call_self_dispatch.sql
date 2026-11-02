-- ################################################################################################
-- # 373 - after closing, the on-call driver takes the will-call themselves, and the office looks
-- # at it in the morning.
-- #
-- # Nobody is in the office to press Passenger Called. The on-call driver takes the call, says in
-- # the app that they are going, and the leg is theirs - through the same checks an assignment
-- # from the office goes through. That it was taken this way is kept on the leg, and so is the
-- # office's review of it the next morning: until it has been looked at, it is not billed.
-- ################################################################################################

ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS selfassignedon DATETIME NULL AFTER brokerstate;
ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS afterhoursreviewedon DATETIME NULL AFTER selfassignedon;
ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS afterhoursreviewedby VARCHAR(36) NULL AFTER afterhoursreviewedon;
