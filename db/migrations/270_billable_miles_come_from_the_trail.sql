-- Billable miles come from the trail.
--
-- Three ways to answer "how far was that trip" and they do not agree. Straight line between
-- two coordinates understates every journey. Road distance from a routing service is an
-- estimate of a route that may not be the one driven - a diversion, a second stop, traffic
-- sent the driver another way. The GPS trail is what the vehicle actually did, and when a
-- broker asks how the figure was reached it is the only one of the three with an answer.
--
-- So the miles are measured from the fixes, and WRITTEN DOWN when the leg closes. Not
-- recomputed on demand: a road changes, a fix is withdrawn, and a trip billed in March must
-- not quietly become a different number in June. The figure and how it was arrived at are
-- both kept, because "how did you get 7.6 miles" is a question with consequences.

ALTER TABLE triplegs
  ADD COLUMN IF NOT EXISTS miles       DECIMAL(7,2) NULL,
  -- gps      - summed from the vehicle's own fixes across the leg. The best evidence.
  -- road     - a routing service's distance for the booked addresses. An estimate.
  -- straight - the direct line between the two points. A floor, never a bill.
  -- manual   - somebody typed it, which happens and should be visible when it does.
  ADD COLUMN IF NOT EXISTS milessource VARCHAR(12)  NULL,
  ADD COLUMN IF NOT EXISTS milesfixes  INT          NULL,
  ADD COLUMN IF NOT EXISTS milesonf    DATETIME     NULL,
  -- Whether the passenger was aboard. A run out to collect somebody is deadhead and most
  -- contracts do not pay for it, so a leg that cannot say which it is cannot be billed
  -- correctly. Booked legs set it; the first leg of a collection is unloaded.
  ADD COLUMN IF NOT EXISTS loaded      TINYINT(1)   NULL;
