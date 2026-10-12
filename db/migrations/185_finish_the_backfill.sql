-- ################################################################################################
-- # 185 - finish what 184 started, and keep the two readings in step.
-- #
-- # 184 marked the records already on file as read so the new rule would start from today, and it
-- # missed three sources: signatures, licence copies and road tests. The consequence was immediate
-- # and exactly what the backfill existed to prevent - every document a driver had already signed
-- # and somebody had already read went back to "waiting to be checked".
-- #
-- # The second half matters more. Several paths already had their own way of saying a thing had
-- # been read: a signing request reviewed, an upload request reviewed, a road test reviewed. Those
-- # must mean the same thing as a row here, or there are two mechanisms disagreeing about one fact,
-- # which is the thing this whole change was meant to end. They are translated in now, and the
-- # endpoints that set them write here as well from this point on.
-- ################################################################################################

INSERT IGNORE INTO documentreads (recordid, accountid, subject, subjectid, sourcetable, sourceid, note)
SELECT UUID(), s.accountid, 'driver', s.ownerid, 'documentsignatures', s.recordid,
       'On file before reading was recorded.'
  FROM documentsignatures s
 WHERE s.ownertype = 'driver';

INSERT IGNORE INTO documentreads (recordid, accountid, subject, subjectid, sourcetable, sourceid, note)
SELECT UUID(), accountid, 'driver', driverid, 'driverlicenses', recordid,
       'On file before reading was recorded.'
  FROM driverlicenses
 WHERE copydocumentid IS NOT NULL;

INSERT IGNORE INTO documentreads (recordid, accountid, subject, subjectid, sourcetable, sourceid, note)
SELECT UUID(), accountid, 'driver', driverid, 'roadtests', recordid,
       'On file before reading was recorded.'
  FROM roadtests;

INSERT IGNORE INTO documentreads (recordid, accountid, subject, subjectid, sourcetable, sourceid, note)
SELECT UUID(), accountid, 'driver', driverid, 'employerinquiries', recordid,
       'On file before reading was recorded.'
  FROM employerinquiries
 WHERE respondedon IS NOT NULL;
