-- ################################################################################################
-- # 071 - qualifications for the other three: vehicles, payers and the company itself.
-- #
-- # The account's list held only what is asked of a driver, so the page that showed it was called
-- # driver qualifications and quietly carried every source - including what a broker asks and what
-- # the company keeps for itself - under that one heading.
-- #
-- # The list now covers each subject the catalog knows, and is read four ways: what is asked of a
-- # driver, of a vehicle, by a broker or payer, and of the company. A requirement that comes from a
-- # contract rather than from law is read with the payer, whichever subject it attaches to, because
-- # that is who it must be answered to.
-- ################################################################################################
ALTER TABLE accountqualifications
    ADD COLUMN subject VARCHAR(8) NOT NULL DEFAULT 'driver' AFTER accountid,
    ADD CONSTRAINT ck_accountqual_subject CHECK (subject IN ('driver', 'vehicle', 'company'));

UPDATE accountqualifications q JOIN compliancedocs c ON c.code = q.code SET q.subject = c.subject;

-- Vehicles and the company start the way drivers did: what the rule plainly requires is on, what
-- turns on something only the company knows starts off.
INSERT IGNORE INTO accountqualifications
    (recordid, accountid, subject, code, catalog, stage, applies, obligation, requiredfor, expires,
     validdays, sortorder)
SELECT UUID(), a.recordid, c.subject, c.code, 1, COALESCE(c.stage, 'prehire'),
       CASE WHEN c.classification = 'required' THEN 'both' ELSE 'off' END,
       c.obligation, c.requiredfor, c.expires, c.validdays, c.sortorder
FROM accounts a
CROSS JOIN compliancedocs c
WHERE a.deleted IS NULL AND a.platform = 0 AND c.active = 1 AND c.subject IN ('vehicle', 'company');
