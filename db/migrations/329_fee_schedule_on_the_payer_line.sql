-- ################################################################################################
-- # 329 - a payer's state line names its fee schedule.
-- #
-- # A schedule used to say who it priced - the passenger, a kind of payer, named payers, a state -
-- # and the pricing worked out which one won. Now the payer's line for a state names the schedule
-- # it is paid under, so there is nothing to work out: a schedule is a price list, and the line is
-- # where it is applied.
-- #
-- # A schedule also remembers the one it replaced, so a line still pointing at a replacement that
-- # has not started yet is priced from the one it replaces until it does.
-- #
-- # Each existing line is given the schedule the old rules would have chosen for it today.
-- ################################################################################################

ALTER TABLE companycontracts ADD COLUMN IF NOT EXISTS scheduleid VARCHAR(36) NULL AFTER program;
ALTER TABLE payerschedules ADD COLUMN IF NOT EXISTS supersedes VARCHAR(36) NULL AFTER name;

UPDATE companycontracts c
SET c.scheduleid = (
  SELECT s.recordid FROM payerschedules s
  WHERE s.accountid = c.accountid AND s.active = 1
    AND (s.state IS NULL OR s.state = c.state)
    AND s.effectivefrom <= CURDATE() AND (s.effectiveto IS NULL OR s.effectiveto >= CURDATE())
    AND ((c.payerid IS NULL AND s.privatepay = 1)
         OR (c.payerid IS NOT NULL
             AND (EXISTS (SELECT 1 FROM schedulepayers sp
                           WHERE sp.scheduleid = s.recordid AND sp.payerid = c.payerid)
                  OR FIND_IN_SET((SELECT p.category FROM payers p WHERE p.recordid = c.payerid),
                                 s.payerkinds) > 0)))
  ORDER BY EXISTS (SELECT 1 FROM schedulepayers sp
                    WHERE sp.scheduleid = s.recordid AND sp.payerid = c.payerid) DESC,
           s.state IS NOT NULL DESC, s.effectivefrom DESC
  LIMIT 1)
WHERE c.scheduleid IS NULL;
