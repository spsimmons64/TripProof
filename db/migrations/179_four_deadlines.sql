-- ################################################################################################
-- # 179 - four deadlines, and the clock that makes the fourth one mean something.
-- #
-- # The engine has had four stages for a while - prehire, predrive, athire, ongoing - and three of
-- # them were doing nothing. Everything federal sat in `prehire` whatever its own text said, so the
-- # screen could say "Before driving" under the road test while the dashboard counted it as a
-- # reason the driver could not be hired. The words and the arithmetic disagreed, and the words
-- # were the ones telling the truth.
-- #
-- # What each stage means, now that all four are used:
-- #
-- #   prehire   must be done before the company may take the person on. Paperwork of employment.
-- #   predrive  must be done before the person may perform safety-sensitive functions. The company
-- #             may hire them; it may not put them in a vehicle. 382.301 and 391.31 are both of
-- #             this kind - neither regulation says a word about the employer's HR moment.
-- #   athire    owed after taking somebody on, by a deadline counted from the hire date.
-- #   ongoing   comes round again for as long as they work here.
-- #
-- # `duedays` is what makes `athire` a deadline rather than a label: 391.23(d) gives thirty days
-- # from the start of employment, and without a number there is nothing to count down to and
-- # nothing can ever be late.
-- ################################################################################################

ALTER TABLE compliancerules ADD COLUMN duedays INT NULL AFTER duestage;

-- ------------------------------------------------------------------------------------------------
-- Before driving, not before hiring.
--
-- 382.301 forbids performing safety-sensitive functions before a negative result; 391.31 is about
-- operating the vehicle; 391.43 certifies the person medically qualified to drive one. A company
-- may hire against any of these contingent on completion, and several do.
-- ------------------------------------------------------------------------------------------------
UPDATE compliancerules
   SET duestage = 'predrive', duetext = NULL
 WHERE subject = 'driver' AND effectiveto IS NULL
   AND code IN ('ROAD_TEST', 'MEDICAL_CERT');

UPDATE compliancerules
   SET duestage = 'predrive', duetext = 'Before performing safety-sensitive functions'
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'PREEMPLOYMENT_DRUG_TEST';

-- ------------------------------------------------------------------------------------------------
-- Owed after hire, by a date.
--
-- The inquiry may be sent before anybody is taken on and usually is. What 391.23(d) fixes is the
-- deadline, and it runs from the start of employment - so it cannot be a reason to refuse the hire,
-- and it has to go late on its own when the thirty days pass.
-- ------------------------------------------------------------------------------------------------
UPDATE compliancerules
   SET duestage = 'athire', duedays = 30, duetext = 'Within 30 days of the hire date'
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'SAFETY_PERFORMANCE_HISTORY';

-- ------------------------------------------------------------------------------------------------
-- The general consent is for the queries that come after.
--
-- 382.701(a) runs on the driver's own electronic consent inside the Clearinghouse, which this does
-- not replace and never did. What the general consent buys is the limited queries - the annual one
-- and any others - so it belongs with the recurring obligations rather than standing between the
-- company and a hire it is not needed for.
-- ------------------------------------------------------------------------------------------------
UPDATE compliancerules
   SET duestage = 'ongoing', duetext = 'Before the first limited query'
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'CLEARINGHOUSE_CONSENT';

-- ------------------------------------------------------------------------------------------------
-- Two lists, two requirements.
--
-- The LEIE and SAM.gov are not one obligation wearing two names. The LEIE carries OIG exclusions
-- and follows the federal health care payment prohibition; SAM.gov carries government-wide
-- debarment and is screened because a contract or a programme says so. Running them together meant
-- a company that owed one appeared to owe both, and a company that owed neither still saw the row.
--
-- The existing requirement becomes the LEIE one, so every screening already on file keeps the
-- requirement it was filed against.
-- ------------------------------------------------------------------------------------------------
UPDATE compliancerules
   SET code = 'EXCLUSION_OIG_LEIE',
       name = 'OIG LEIE Exclusion Screening',
       authority = 'HHS OIG',
       citation = '42 CFR 1001.1901 - federal health care program payment prohibition',
       evidencesource = 'exclusioncheck:OIG_LEIE',
       note = 'A federal health care program may not pay for services furnished by an excluded '
              'person, which reaches transportation. OIG treats the LEIE as the primary way to '
              'find its exclusions and expects screening before hiring and monthly afterwards.'
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'EXCLUSION_CHECK_DRIVER';

INSERT INTO compliancerules (recordid, subject, code, name, authoritytype, authority, citation,
                             applieswhen, evidencekind, evidencesource, alternatesource,
                             alternatewhen, reviewrequired, determination, blocking, gate, grouping,
                             duestage, duedays, duetext, recurrence, recurrencedays, warndays, note,
                             sortorder, effectivefrom)
SELECT UUID(), 'driver', 'EXCLUSION_SAM_GOV', 'SAM.gov Exclusion and Debarment Screening',
       'contract', 'GSA SAM', 'Federal contract, grant or programme requirement',
       '{"fact":"company.samgov","is":true}', evidencekind, 'exclusioncheck:SAM_EXCLUSIONS',
       NULL, NULL, reviewrequired, determination, blocking, gate, grouping,
       duestage, duedays, duetext, recurrence, recurrencedays, warndays,
       'The government-wide exclusions list. Screened where a federal contract, grant or programme '
       'asks for it rather than because somebody is excluded by OIG.',
       sortorder + 1, CURRENT_DATE
  FROM compliancerules
 WHERE subject = 'driver' AND effectiveto IS NULL AND code = 'EXCLUSION_OIG_LEIE';

-- Whether this company owes the SAM screening at all. Unanswered is not "no": until somebody says,
-- the requirement reads as unknown rather than quietly disappearing.
INSERT INTO companyquestions (code, factname, question, help, sortorder) VALUES
  ('SAM_SCREENING', 'company.samgov',
   'Does a contract, grant or programme require SAM.gov exclusion screening?',
   'Separate from the OIG LEIE check. SAM.gov carries government-wide debarment information, and '
   'the obligation to screen it comes from what you have signed rather than from the exclusion '
   'statute. Turns on the SAM.gov screening requirement for drivers.', 35)
ON DUPLICATE KEY UPDATE question = VALUES(question), help = VALUES(help);
