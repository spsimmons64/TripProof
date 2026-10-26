-- ################################################################################################
-- # 356 - a will-call return has no pickup time until the passenger rings.
-- #
-- # The board, the driver app, dispatch and the trip check were all written for a leg with no
-- # pickup time - the check reads such a leg as of the trip's date - but the column itself still
-- # refused one, so no will-call could ever be booked. The time is written when the passenger
-- # calls (POST /legs/{id}/release).
-- ################################################################################################

ALTER TABLE triplegs MODIFY pickupat DATETIME NULL;
