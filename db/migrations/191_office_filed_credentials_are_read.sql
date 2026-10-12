-- ################################################################################################
-- # 191 - a credential somebody in this office filed has been read by somebody in this office.
-- #
-- # 184 made every rule declare where its evidence comes from, so that a document made outside this
-- # office cannot go green until a person here says they have read it. 188's counterpart to that -
-- # record the reading at the moment of filing, because whoever typed the dates off the paper was
-- # holding the paper - was wired into ten filing paths and missed the eleventh: the credential
-- # endpoint, which is what files a medical certificate, every training certificate, a Level 1
-- # screening and a Clearinghouse query credential.
-- #
-- # So an office that uploaded a medical certificate was shown a blue eye asking them to review the
-- # document they had just read well enough to transcribe. The code is fixed; this is for the
-- # records filed in between, and for anything from before the rule existed.
-- #
-- # `enteredby` is what tells them apart and it is reliable: the office endpoint writes the user who
-- # filed it, and a credential created from a driver's own upload leaves it null - that one came
-- # from outside and the upload request's own reviewed date governs it, as it always has.
-- ################################################################################################

INSERT IGNORE INTO documentreads (recordid, accountid, subject, subjectid, sourcetable, sourceid,
                                  readby, note)
SELECT UUID(), c.accountid, 'driver', c.subjectid, 'credentials', c.recordid, c.enteredby,
       'Filed by the office.'
  FROM credentials c
 WHERE c.subject = 'driver' AND c.enteredby IS NOT NULL
   AND c.deleted IS NULL AND c.revokedon IS NULL;
