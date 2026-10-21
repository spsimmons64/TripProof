-- ################################################################################################
-- # 332 - driving experience is read off the licenses on file.
-- #
-- # A license's issue date is usually its latest renewal, so it proves a driver was licensed by
-- # then and no earlier. Where the card prints an original issue date it is recorded beside the
-- # issue date, and that is the start of the driver's driving. The separate "First Licensed" field
-- # on the driver goes; whatever was typed into it is carried onto the driver's active license (or
-- # the oldest, where none is marked active) as that license's original issue date.
-- ################################################################################################

ALTER TABLE driverlicenses ADD COLUMN IF NOT EXISTS originalissued DATE NULL AFTER issued;

UPDATE driverlicenses l
JOIN drivers d ON d.recordid = l.driverid
SET l.originalissued = d.licensesince
WHERE d.licensesince IS NOT NULL AND l.originalissued IS NULL
  AND l.recordid = (SELECT x.recordid FROM driverlicenses x WHERE x.driverid = d.recordid
                    ORDER BY x.active DESC, COALESCE(x.issued, '9999-12-31') ASC LIMIT 1);
