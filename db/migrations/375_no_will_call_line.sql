-- ################################################################################################
-- # 375 - the will-call line is withdrawn.
-- #
-- # A Twilio number belongs to TripProof, not to a company, and a will-call reaches a provider by
-- # the broker's own route (Ride Assist) or the company's own telephone. What matters is who is
-- # responsible for the return and when it was activated, which the trip itself now records. The
-- # on-call texts (oncalltexts) stay.
-- ################################################################################################

DROP TABLE IF EXISTS linecalls;
ALTER TABLE accounts DROP COLUMN IF EXISTS willcallnumber;
ALTER TABLE accounts DROP COLUMN IF EXISTS officephone;
