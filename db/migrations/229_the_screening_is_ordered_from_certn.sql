-- ################################################################################################
-- # 229 - the background screening is ordered from Certn, so the order has to remember them.
-- #
-- # The PSP report and the CDLIS check are ordered by somebody signing in to a government site and
-- # bringing the answer back. This one is ordered by TripProof over an API, which changes what the
-- # record has to hold: whose order it is at the other end, what they last said about it, and what
-- # we charged for it.
-- #
-- # `vendorref` is THEIR id for the application. Without it a webhook arriving in six hours cannot
-- # be matched to the driver it belongs to, and a result would land with nowhere to go.
-- #
-- # `chargecents` is what was charged at the time, not what the tier costs today. A price list
-- # changes; what a company paid in March does not, and an invoice somebody queries in a year has
-- # to be answerable from the record rather than from whatever the price happens to be then.
-- ################################################################################################

ALTER TABLE driverreports
  ADD COLUMN IF NOT EXISTS vendor       VARCHAR(16)  NULL AFTER tier,
  ADD COLUMN IF NOT EXISTS vendorref    VARCHAR(64)  NULL AFTER vendor,
  ADD COLUMN IF NOT EXISTS vendorstatus VARCHAR(32)  NULL AFTER vendorref,
  ADD COLUMN IF NOT EXISTS chargecents  INT          NULL AFTER vendorstatus,
  ADD COLUMN IF NOT EXISTS lastsyncedon DATETIME     NULL AFTER chargecents;

-- One order per application at the vendor, so a webhook delivered twice cannot make two records.
CREATE UNIQUE INDEX IF NOT EXISTS ux_driverreports_vendorref
  ON driverreports (accountid, vendor, vendorref);
