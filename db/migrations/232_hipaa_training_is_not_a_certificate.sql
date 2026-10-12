-- HIPAA training, as the rule actually reads.
--
-- There is no federally issued "HIPAA training certificate". HHS does not approve courses, does
-- not appoint trainers and does not issue certificates. 45 CFR 164.530(b)(1) requires a covered
-- entity to train its workforce on its OWN policies and procedures, as necessary and appropriate
-- for each person to carry out their function, and to document that it happened -
-- 45 CFR 164.530(j). 45 CFR 164.308(a)(5)(i) separately requires an ongoing security awareness
-- and training programme. Neither names a document.
--
-- So the requirement was wrong in three ways and each one would have put a false statement in
-- front of an operator:
--
--   1. It was CALLED a certificate, which told a company it had to go and buy one. A company that
--      trains its own drivers and writes down that it did so has complied, and was being told it
--      had not.
--   2. It EXPIRED after 365 days. Federal HIPAA sets no interval. Retraining is owed when the
--      company's policies or procedures materially change in a way that affects the person's job,
--      which is an event, not a date. A broker may impose an annual cycle, and where it does the
--      certificate it issues carries the date - which is what 'ondocument' reads.
--   3. It cited only the Privacy Rule, so the Security Rule's awareness requirement went unsaid.
--
-- What does NOT change: who it applies to. It is still asked only where the company is a covered
-- entity or a business associate, and still owed within 30 days of hire.

-- 600 characters was enough while a description was a sentence. A rule that has to say what the
-- training must actually cover, and who may give it, does not fit in one.
ALTER TABLE compliancerules MODIFY COLUMN description VARCHAR(1200) NULL;

UPDATE compliancerules
   SET name = 'HIPAA privacy and security training',
       description = CONCAT(
         'Training in handling protected health information, for a driver working for a HIPAA ',
         'covered entity or its business associate. For a driver that means the manifest, ',
         'passenger names and addresses, the medical destination, what is said in the vehicle, ',
         'phones and dispatch messages, what may be told to a family member or facility staff, ',
         'lost paperwork, and how to report a suspected breach. The company may deliver the ',
         'training itself, buy a course, or be required by a broker to use the broker''s own ',
         'module. Evidence is a certificate of completion or the company''s own dated record of ',
         'the training given.'),
       citation = '45 CFR 164.530(b)(1); 45 CFR 164.308(a)(5)(i)',
       -- No federal interval. It goes out of date when the evidence itself says it does, which is
       -- how a broker's annual module reaches this rule without the rule inventing an annual
       -- requirement that federal law does not impose.
       recurrence = 'ondocument',
       recurrencedays = NULL,
       duetext = 'Within 30 days of hire, and again whenever policies change materially'
 WHERE code = 'HIPAA_TRAINING_DRIVER';

-- The thing filed against it is a training record, which may or may not have a certificate behind
-- it. Clearing the default validity stops a date being invented for evidence that carries none.
UPDATE credentialtypes
   SET name = 'HIPAA privacy and security training',
       description = 'A certificate of completion, or the company''s own dated record of the '
                     'training it gave. Record who provided it.',
       defaultvaliddays = NULL
 WHERE code = 'HIPAA_TRAINING';
