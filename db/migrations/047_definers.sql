-- ================================================================================================
-- 047 - restamp the view and the triggers as whoever is connected.
--
-- A view or trigger remembers the account that created it, and runs as that account. A database
-- moved between machines carries those names with it, so a dump taken where the login was
-- tripproof@% and loaded where it is tripproof@localhost leaves every one of them pointing at an
-- account that does not exist. MariaDB then reports plain "Access denied for user ... (using
-- password: YES)", which reads exactly like a wrong password.
--
-- Recreating them here stamps the account this migration runs as. The view no longer depends on
-- one at all: SQL SECURITY INVOKER means it runs with the privileges of whoever selects from it,
-- which is what a view over plain tables wants.
-- ================================================================================================

CREATE OR REPLACE SQL SECURITY INVOKER VIEW tripexposure AS
SELECT t.accountid,
       t.recordid      AS tripid,
       t.externalid,
       t.tripdate,
       t.brokerid,
       t.billedamount,
       t.billingstatus,
       t.lastrunid     AS runid,
       COUNT(*)        AS failures
FROM trips t
JOIN legchecks c ON c.tripid = t.recordid AND c.runid = t.lastrunid
WHERE t.deleted IS NULL
  AND c.outcome IN ('fail','nosubject')
GROUP BY t.accountid, t.recordid, t.externalid, t.tripdate, t.brokerid, t.billedamount,
         t.billingstatus, t.lastrunid;

-- Triggers have no invoker option; they can only be recreated under the current account.
DELIMITER $$

CREATE OR REPLACE TRIGGER tr_rulesets_nooverlap_ins BEFORE INSERT ON rulesets FOR EACH ROW
BEGIN
    IF EXISTS (SELECT 1 FROM rulesets r
               WHERE r.family = NEW.family
                 AND r.effectivefrom <= COALESCE(NEW.effectiveto, '9999-12-31')
                 AND COALESCE(r.effectiveto, '9999-12-31') >= NEW.effectivefrom) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'rulesets: overlapping versions in one family';
    END IF;
END$$

CREATE OR REPLACE TRIGGER tr_rulesets_nooverlap_upd BEFORE UPDATE ON rulesets FOR EACH ROW
BEGIN
    IF EXISTS (SELECT 1 FROM rulesets r
               WHERE r.family = NEW.family
                 AND r.recordid <> NEW.recordid
                 AND r.effectivefrom <= COALESCE(NEW.effectiveto, '9999-12-31')
                 AND COALESCE(r.effectiveto, '9999-12-31') >= NEW.effectivefrom) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'rulesets: overlapping versions in one family';
    END IF;
END$$

CREATE OR REPLACE TRIGGER tr_activitylog_noupdate BEFORE UPDATE ON activitylog FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'activitylog is append-only';
END$$

CREATE OR REPLACE TRIGGER tr_activitylog_nodelete BEFORE DELETE ON activitylog FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'activitylog is append-only';
END$$

CREATE OR REPLACE TRIGGER tr_legchecks_noupdate BEFORE UPDATE ON legchecks FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'legchecks are immutable';
END$$

DELIMITER ;
