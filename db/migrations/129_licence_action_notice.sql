-- ################################################################################################
-- # 129 - the suspension acknowledgement follows the driver's own answer.
-- #
-- # F.A.C. 14-90.006(1) is about drivers whose licence has been acted against, and the application
-- # already asks them: "Has your license ever been revoked, or have you ever been denied a license,
-- # in the last 3 years?". Asked of every covered driver regardless, the requirement was noise on
-- # the file of everybody who answered no.
-- #
-- #   said no          the rule does not reach them             blue dash
-- #   said yes         it reaches them, and nothing is on file  grey question
-- #   said yes, filed  the documentation answers it             green tick
-- #   not asked        nobody has said, so nothing is decided   grey question
-- #
-- # The answer is read from the application itself rather than copied onto the driver, so it cannot
-- # drift from what they signed. Three-valued, so an unanswered application never reads as "no".
-- #
-- # The rule had nowhere to file an answer - `evidencesource` was null, which the engine reports as
-- # "there is nowhere in TripProof to record it yet". It now takes a document, so what the driver
-- # provides can actually be filed against it.
-- ################################################################################################

INSERT INTO credentialtypes (recordid, code, name, subject, active)
SELECT UUID(), 'FL_LICENSE_ACTION', 'Licence revocation or denial documentation', 'driver', 1
 WHERE NOT EXISTS (SELECT 1 FROM credentialtypes WHERE code = 'FL_LICENSE_ACTION');

UPDATE compliancerules
   SET applieswhen = '{"all":[{"fact":"driver.chapter1490","is":true},'
                     '{"fact":"driver.licenceaction","is":true}]}',
       evidencekind = 'document',
       evidencesource = 'credential:FL_LICENSE_ACTION'
 WHERE code = 'FL_LICENSE_STATUS_NOTICE' AND subject = 'driver';
