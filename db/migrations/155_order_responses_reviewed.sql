-- ################################################################################################
-- # 155 - a response to an order is read before it counts.
-- #
-- # There are two ways a report gets onto a driver's file and they are not the same act.
-- #
-- #   Somebody in the office UPLOADS one. They had it open in front of them, and the finding they
-- #   recorded as they filed it IS their reading of it.
-- #
-- #   An ORDER comes back. Nobody has read it. It arrived because somebody asked for it days ago,
-- #   and it may say anything at all - that is the whole reason it was asked for.
-- #
-- # So every report that answers a requirement is marked as needing a reading, and a response filed
-- # against an order lands unread. The requirement does not go green on a document nobody in the
-- # office has looked at, which is the gap nobody notices until an auditor finds it.
-- ################################################################################################

UPDATE compliancerules
   SET reviewrequired = 1
 WHERE subject = 'driver' AND effectiveto IS NULL AND evidencesource LIKE 'report:%';
