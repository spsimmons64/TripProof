-- ################################################################################################
-- # 121 - a request can be withdrawn.
-- #
-- # A request out on a licence blocks everything else on it: no second request, no record filed by
-- # hand, because two answers with nothing to say which belongs to which question is worse than one.
-- # That is right while the request is genuinely out - and a trap the moment one is placed by
-- # mistake, or asked of the wrong authority, or abandoned because the answer is never coming. The
-- # licence would be blocked for good.
-- #
-- # So a request can be withdrawn. Withdrawn, not deleted: somebody asked a licensing authority a
-- # question on a date, often for money, and that happened whether or not it was a good idea. The
-- # row stays and says when it was called off and by whom, and stops counting as outstanding.
-- ################################################################################################

ALTER TABLE drivermvrs
    ADD COLUMN IF NOT EXISTS cancelledon DATETIME    NULL AFTER receivedby,
    ADD COLUMN IF NOT EXISTS cancelledby VARCHAR(36) NULL AFTER cancelledon;
