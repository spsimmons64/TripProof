-- Where each document came from, recorded when it is stored.
--
-- The office may take back a file it filed against the wrong driver. It may not take back the
-- driver's own submission, what a service returned, or what a previous employer sent: those are
-- somebody else's record of what they did, and a carrier that can quietly remove them can
-- quietly remove the inconvenient ones.
--
-- WHY THIS IS STAMPED AND NOT INFERRED
--
-- The obvious reading is documents.uploadedby - office uploads have a user, outside ones do not.
-- It does not hold. Of the six documents that arrived through an upload link on the live
-- account, one carries a user and five do not, so that column would wrongly protect some office
-- uploads and wrongly expose some drivers'. Origin is only known for certain at the moment the
-- bytes are stored, by whoever is storing them, so that is where it is written down.
--
-- NULL IS NOT WITHDRAWABLE
--
-- The backfill below establishes what it can prove and leaves the rest NULL, and NULL is locked.
-- In a compliance file "we are not sure where this came from" must never mean "so you may delete
-- it". It also makes the code fail safe: a call site that forgets to say `office` produces a file
-- nobody can withdraw, which is harmless. Removing one takes a positive assertion that the office
-- put it there.

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS origin varchar(12) DEFAULT NULL;

-- What arrived through the driver's own upload link.
UPDATE documents d
   SET d.origin = 'driver'
 WHERE d.origin IS NULL
   AND EXISTS (SELECT 1 FROM uploadrequests r
                WHERE r.documentid = d.recordid AND r.accountid = d.accountid);

-- What a service sent back, having been ordered from here.
UPDATE documents d
   SET d.origin = 'service'
 WHERE d.origin IS NULL
   AND (EXISTS (SELECT 1 FROM driverreports x
                 WHERE x.documentid = d.recordid AND x.accountid = d.accountid
                   AND x.orderedon IS NOT NULL)
     OR EXISTS (SELECT 1 FROM drivermvrs x
                 WHERE x.documentid = d.recordid AND x.accountid = d.accountid
                   AND x.orderedon IS NOT NULL));

-- What a previous employer sent in answer to a safety performance history inquiry.
UPDATE documents d
   SET d.origin = 'thirdparty'
 WHERE d.origin IS NULL
   AND (EXISTS (SELECT 1 FROM employerinquiries x
                 WHERE x.accountid = d.accountid
                   AND (x.documentid = d.recordid OR x.effortdocumentid = d.recordid))
     OR EXISTS (SELECT 1 FROM employerinquiryattempts x
                 WHERE x.documentid = d.recordid));

-- Everything else stays NULL. It is not evidence the office filed it - only that nobody can
-- show who did - and that is exactly the case to leave alone.

-- And what the office can be SHOWN to have filed.
--
-- The first pass left 116 of 126 documents unknown, which is the right default but makes the
-- feature useless on everything that already exists. This is not a guess at the remainder: a
-- document hanging on a credential, a licence copy, a test, an accident or a prohibition, where
-- no upload request and no ordered report claims it, got there because somebody in the office
-- put it there. There is no other way for it to be attached to one of those records.
--
-- Anything that still does not match stays NULL and stays locked.

UPDATE documents d
   SET d.origin = 'office'
 WHERE d.origin IS NULL
   AND NOT EXISTS (SELECT 1 FROM uploadrequests r
                    WHERE r.accountid = d.accountid AND r.documentid = d.recordid)
   AND (EXISTS (SELECT 1 FROM credentials x
                 WHERE x.accountid = d.accountid AND x.documentid = d.recordid)
     OR EXISTS (SELECT 1 FROM driverlicenses x
                 WHERE x.accountid = d.accountid AND x.copydocumentid = d.recordid)
     OR EXISTS (SELECT 1 FROM drugtests x
                 WHERE x.accountid = d.accountid AND x.documentid = d.recordid)
     OR EXISTS (SELECT 1 FROM driverprohibitions x
                 WHERE x.accountid = d.accountid
                   AND (x.documentid = d.recordid OR x.sapinfodocumentid = d.recordid)));
