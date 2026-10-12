-- ################################################################################################
-- # 218 - the licence a driver photographed on their application reaches their licence file.
-- #
-- # Two holes, and together they made the application look like it had collected nothing.
-- #
-- #  1. STEP 2 NEVER WROTE A LICENCE RECORD. It put the number, the state and the class onto the
-- #     `drivers` row and stopped there. Both licence requirements read `driverlicenses`, so a
-- #     driver who completed the whole application had nothing for either of them to look at. Fixed
-- #     in the application itself; this migration is for the ones already submitted.
-- #
-- #  2. THE PHOTOGRAPH WAS NEVER LINKED. `license_front` was stored against the application in
-- #     `driverapplications.data.uploads` and nothing ever pointed a licence record at it. So the
-- #     requirement said "Nothing on file yet" about a card the driver had photographed and sent
-- #     in, which is the complaint that found this.
-- #
-- # The backfill links the photograph to the active licence where there is one and no copy already
-- # recorded. It does NOT mark it read. A licence copy comes from the driver, the rule says so, and
-- # a photograph nobody here has looked at is exactly what "waiting to be reviewed" is for - these
-- # will move to needing review rather than straight to green, which is the honest answer.
-- ################################################################################################

UPDATE driverlicenses l
  JOIN (
      SELECT a.driverid, a.accountid,
             JSON_UNQUOTE(JSON_EXTRACT(a.data, '$.uploads.license_front.documentid')) AS documentid
        FROM driverapplications a
       WHERE JSON_EXTRACT(a.data, '$.uploads.license_front.documentid') IS NOT NULL
  ) AS sent
    ON sent.driverid = l.driverid AND sent.accountid = l.accountid
  JOIN documents d ON d.recordid = sent.documentid
   SET l.copydocumentid = sent.documentid, l.updated = UTC_TIMESTAMP()
 WHERE l.active = 1 AND l.copydocumentid IS NULL;
