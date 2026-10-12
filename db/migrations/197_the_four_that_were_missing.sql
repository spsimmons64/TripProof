-- ################################################################################################
-- # 197 - four things a driver qualification file is supposed to establish and this one did not.
-- #
-- # Found by auditing a complete, fully green CDL driver against 49 CFR 391 Subpart C and Part 382.
-- # Every one of these would have been a finding, and three of the four could not be answered by
-- # anything on the screen at all.
-- #
-- #  1. A VALID LICENCE. The only licence rule in the catalog was conditioned on the company
-- #     carrying Medicaid trips and cited to 42 U.S.C. 1396a - it exists because Medicaid asks for
-- #     a copy, not because 391.11(b)(5) requires the driver to hold one. A carrier with no
-- #     Medicaid work had NO licence requirement: nothing asked for one, nothing checked the class,
-- #     nothing noticed it expiring. The Medicaid rule stays as it is; this is the other one.
-- #
-- #  2. AGE. 391.11(b)(1) is twenty-one for interstate commerce. The date of birth has been on the
-- #     record all along and nothing ever looked at it. A nineteen-year-old passed every check.
-- #
-- #  3. POST-ACCIDENT TESTING. The accident register and the whole 382.303 decision tree were
-- #     built, and when the decision said a test was owed, no requirement ever appeared. The engine
-- #     knew and the file did not say - which is the worst shape to be in, because the obligation
-- #     is recorded and its discharge is not.
-- #
-- #  4. THE AT-HIRE DEADLINES. `duestage: athire` grew a clock weeks ago and only the safety
-- #     performance history was ever given a number. The I-9 has a statutory deadline measured in
-- #     business days and would have sat at "nothing on file yet" for ever.
-- ################################################################################################

-- 1 ------------------------------------------------------------------------------------------
-- Reads the licence record rather than a copy of it: the question is whether the driver holds a
-- current one, which is true or false whether or not anybody has photographed the card.
INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype, authority,
                             citation, applieswhen, evidencekind, evidencesource, origin,
                             extendable, extendnote, reviewrequired, determination, blocking, gate,
                             grouping, duestage, duetext, recurrence, warndays, note, sortorder,
                             effectivefrom)
VALUES (UUID(), 'driver', 'DRIVER_LICENCE', 'Valid driver''s license',
        'The driver must hold a current license of the class the vehicle requires. TripProof reads '
        'the license record itself, so it goes amber as the expiry approaches and stops the driver '
        'the day it passes - whether or not a copy of the card is on file.',
        'regulation', 'FMCSA', '49 CFR 391.11(b)(5)', NULL,
        'document', 'licence', 'office', 0,
        'Every driver needs a license. There is nothing to extend.',
        0, 0, 1, 'hardstop', 'regulatory', 'predrive', NULL, 'ondocument', 30, NULL, 10,
        CURRENT_DATE);

-- 2 ------------------------------------------------------------------------------------------
-- Answered by what is already known rather than by a document. It reaches only the drivers the
-- rule is about, and a driver whose date of birth is missing reads as unknown rather than as
-- qualified - the software does not vouch for something nobody has told it.
INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype, authority,
                             citation, applieswhen, evidencekind, evidencesource, origin,
                             extendable, extendnote, reviewrequired, determination, blocking, gate,
                             grouping, duestage, duetext, recurrence, warndays, note, sortorder,
                             effectivefrom)
VALUES (UUID(), 'driver', 'DRIVER_AGE', 'Minimum age for interstate operation',
        'A driver must be at least 21 years old to operate a commercial motor vehicle in '
        'interstate commerce. Read from the date of birth on the driver record; there is nothing '
        'to file.',
        'regulation', 'FMCSA', '49 CFR 391.11(b)(1)',
        '{"all":[{"fact":"operation.interstate","is":true},{"fact":"driver.cmv","is":true}]}',
        'fact', 'driverfact:driver.age21', 'office', 0,
        'An age limit is not something a company can choose to apply more widely.',
        0, 1, 1, 'hardstop', 'regulatory', 'prehire', NULL, 'once', 30, NULL, 5, CURRENT_DATE);

-- 3 ------------------------------------------------------------------------------------------
-- Reaches the driver only once an accident on their register has called for a test and the test
-- is not on file. Satisfied by the post-accident test itself, through the evidence the testing
-- panel already files.
INSERT INTO compliancerules (recordid, subject, code, name, description, authoritytype, authority,
                             citation, applieswhen, evidencekind, evidencesource, origin,
                             extendable, extendnote, reviewrequired, determination, blocking, gate,
                             grouping, duestage, duetext, recurrence, warndays, note, sortorder,
                             effectivefrom)
VALUES (UUID(), 'driver', 'POSTACCIDENT_TEST', 'Post-accident controlled substances and alcohol test',
        'An accident on this driver''s register required testing under 49 CFR 382.303 and the '
        'result is not on file. The collection windows - eight hours for alcohol, thirty-two for '
        'controlled substances - govern when it can still be done, not whether it was owed.',
        'regulation', 'FMCSA', '49 CFR 382.303',
        '{"fact":"driver.postaccidentowed","is":true}',
        'test', 'drugtest:postaccident', 'thirdparty', 0,
        'Post-accident testing follows the accident, not a company''s choice.',
        0, 1, 1, 'hardstop', 'regulatory', 'ongoing',
        'As soon as practicable after the accident', 'once', 30,
        'Record the accident first. The register decides whether 382.303 required a test; this '
        'row appears only where it did and the test is not on file.', 210, CURRENT_DATE);

-- 4 ------------------------------------------------------------------------------------------
-- The deadlines. Section 1 of the I-9 is owed by the first day of work and Section 2 within three
-- business days of it; three calendar days is the nearest honest approximation TripProof can make
-- without a working calendar, and it errs early rather than late.
UPDATE compliancerules SET duedays = 3  WHERE subject = 'driver' AND code = 'I9';
UPDATE compliancerules SET duedays = 7  WHERE subject = 'driver' AND code = 'W4';
UPDATE compliancerules SET duedays = 30 WHERE subject = 'driver' AND effectiveto IS NULL
   AND code IN ('HIPAA_TRAINING_DRIVER', 'PASS_TRAINING', 'SECUREMENT_TRAINING_CERT',
                'BBP_TRAINING');
