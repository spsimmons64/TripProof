-- When a driver works.
--
-- "Available" has meant two things: not already on a trip, and qualified to drive. Neither says
-- anything about whether the person is at work. A dispatcher covering a 3am airport run is
-- offered the whole roster, every one of them asleep, and the suggestion engine will rank them by
-- how near their last known position was.
--
-- A weekly pattern, because that is how a small NEMT operation actually runs: Maria does Monday to
-- Friday 6 to 2, Joe does afternoons and alternate Saturdays. Exceptions to it - a day off, a week
-- of training - are already `driverunavailable`, and the two answer different questions: this one
-- is what normally happens, that one is what is happening instead.
--
-- A driver with NO rows here is treated as available at any hour. That is deliberate. The
-- alternative is that adding this table makes every existing driver unavailable overnight, and a
-- product that silently stops working the day it gains a feature is worse than one without it.

CREATE TABLE IF NOT EXISTS drivershifts (
  recordid      VARCHAR(36) NOT NULL PRIMARY KEY,
  accountid     VARCHAR(36) NOT NULL,
  driverid      VARCHAR(36) NOT NULL,
  -- 0 = Monday. ISO order, because a working week starts on Monday everywhere this is read.
  weekday       TINYINT     NOT NULL,
  startsat      TIME        NOT NULL,
  -- An end BEFORE the start means the shift runs past midnight - a 22:00 to 06:00 night turn is
  -- one shift, not two, and splitting it across two rows would lose that.
  endsat        TIME        NOT NULL,
  effectivefrom DATE        NULL,
  effectiveto   DATE        NULL,
  added         DATETIME    NOT NULL,
  addedby       VARCHAR(36) NULL,
  KEY ix_drivershifts (accountid, driverid, weekday)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
