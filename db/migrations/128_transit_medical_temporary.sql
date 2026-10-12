-- ################################################################################################
-- # 128 - a temporary disqualification is one of the results, not a tick beside them.
-- #
-- # It was modelled the way the paper form prints it: three results, with temporary disqualification
-- # among the conditions alongside corrective lenses and the follow-up date. That left two columns
-- # able to disagree - "meets standards" ticked as temporarily disqualified - and only the engine
-- # knowing which of them won.
-- #
-- # One field now says what the examination concluded:
-- #
-- #     meets           qualified, two years unless the examiner shortened it
-- #     meetsperiodic   qualified, until the date the examiner set
-- #     doesnotmeet     not qualified
-- #     temporary       not qualified for now, with a reason and a follow-up date
-- #
-- # `tempreason` and `followupon` stay: they say why and until when, which is the part a temporary
-- # disqualification has that the others do not.
-- ################################################################################################

UPDATE transitmedicals
   SET result = 'temporary', qualifiedthrough = NULL
 WHERE tempdisqualified = 1;

ALTER TABLE transitmedicals
    DROP COLUMN tempdisqualified;
