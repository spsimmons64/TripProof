-- ################################################################################################
-- # 132 - a document the driver sent is not a document anybody has read.
-- #
-- # Everything else on a driver's file was put there by the office: somebody had it open, looked at
-- # it, and filed it. A document that arrives down a link had none of that. It may be the wrong
-- # document, an expired one, a photograph of something else entirely, or a certificate belonging to
-- # somebody with the same name.
-- #
-- # So a requirement does not go green on it. It reads as waiting to be checked until somebody in
-- # the office says they have looked:
-- #
-- #   driver sends it   -> on file, waiting to be checked       teal eye
-- #   office checks it  -> the requirement stands on it         green tick
-- #
-- # The flag lives on the REQUEST rather than on the credential or the licence row, because the
-- # request is the one thing that knows a document came from the driver at all. One place, whatever
-- # kind of record the document ended up as - and nothing to keep in step.
-- ################################################################################################

ALTER TABLE uploadrequests
    ADD COLUMN IF NOT EXISTS reviewedon DATETIME    NULL AFTER credentialid,
    ADD COLUMN IF NOT EXISTS reviewedby VARCHAR(36) NULL AFTER reviewedon;

-- Anything already sent before this existed has been seen by whoever was watching for it.
UPDATE uploadrequests SET reviewedon = uploadedon
 WHERE uploadedon IS NOT NULL AND reviewedon IS NULL;
