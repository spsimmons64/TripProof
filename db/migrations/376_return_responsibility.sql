-- ################################################################################################
-- # 376 - who brings the passenger home, and how a will-call was activated.
-- #
-- # Every return leg says who is responsible for it: the provider (us), another provider that has
-- # confirmed it, or not decided yet - and an undecided return keeps the outbound from being given a
-- # driver. The broker taking it is the hand-back already recorded on the leg (brokerstate): asked
-- # for, the return is still ours; confirmed, it is the broker's.
-- #
-- # A will-call activated is kept with where the word came from (the passenger, the facility, the
-- # broker's portal or telephone, the driver), when it reached us, and - where the broker says - when
-- # the passenger was ready, which is when a broker's pickup clock can start.
-- #
-- # And each broker's own will-call rules, on the company's terms with that payer.
-- ################################################################################################

ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS responsibility VARCHAR(12) NULL AFTER returnplan;
ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS responsibilitynote VARCHAR(255) NULL AFTER responsibility;
ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS activationsource VARCHAR(16) NULL AFTER responsibilitynote;
ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS activatedon DATETIME NULL AFTER activationsource;
ALTER TABLE triplegs ADD COLUMN IF NOT EXISTS brokerreadyat DATETIME NULL AFTER activatedon;
UPDATE triplegs SET responsibility = 'provider' WHERE legnumber > 1 AND responsibility IS NULL;

ALTER TABLE accountpayers ADD COLUMN IF NOT EXISTS pickuplimit SMALLINT NULL AFTER priority;
ALTER TABLE accountpayers ADD COLUMN IF NOT EXISTS clockstarts VARCHAR(12) NULL AFTER pickuplimit;
ALTER TABLE accountpayers ADD COLUMN IF NOT EXISTS afterhourscontact VARCHAR(160) NULL AFTER clockstarts;
ALTER TABLE accountpayers ADD COLUMN IF NOT EXISTS returnprocedure VARCHAR(600) NULL AFTER afterhourscontact;
ALTER TABLE accountpayers ADD COLUMN IF NOT EXISTS confirmationneeded VARCHAR(255) NULL AFTER returnprocedure;
