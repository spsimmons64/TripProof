-- ################################################################################################
-- # 180 - let a driver actually be hired.
-- #
-- # 178 renamed the stored status from 'active' to 'hired' and changed every screen with it, but it
-- # left the CHECK constraint and the column default naming the old word. The UPDATE in that
-- # migration passed only because no driver had been hired yet, so nothing was rewritten and the
-- # constraint was never tested.
-- #
-- # The effect is that "Hire This Driver" would have failed on the constraint the first time
-- # somebody pressed it. Found by setting a hire date in a rolled-back transaction while testing
-- # the after-hire deadlines, which is exactly the kind of thing a constraint is for.
-- ################################################################################################

ALTER TABLE drivers DROP CONSTRAINT ck_drivers_status;

ALTER TABLE drivers
  MODIFY COLUMN status VARCHAR(12) NOT NULL DEFAULT 'application',
  ADD CONSTRAINT ck_drivers_status CHECK (status IN
    ('application', 'appcor', 'new', 'pending', 'hired', 'inactive', 'declined'));
