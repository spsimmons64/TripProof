-- Wheelchair securement training, corrected against what the rules actually say.
--
-- Four things were wrong, and three of them were wrong in the same direction: the requirement
-- described a certificate that no regulation asks for.
--
--   1. THE FLORIDA CITATION WAS WRONG. It pointed at F.A.C. 14-90.004(1), which is the carrier's
--      System Safety Program Plan. The training and testing requirement is 14-90.004(3)(d), and
--      it is a different obligation on a different party. A citation that sends somebody to the
--      wrong paragraph is worse than no citation: they read it, find nothing about training, and
--      conclude the requirement is invented.
--
--   2. THE FEDERAL CITATION WAS HALF THERE. 49 CFR 37.173 is the proficiency requirement;
--      37.165 is what the driver must actually be proficient AT - the securement of mobility
--      devices and the assistance of the passengers using them.
--
--   3. IT EXPIRED AFTER 730 DAYS. Nothing in the ADA regulations sets a recurrent interval, and
--      FTA has said so directly: there is no prescribed refresher cycle, but the employee must
--      REMAIN proficient. Florida 14-90.004(3)(d) sets none either. A two-year clock in the
--      regulatory column, with no regulation behind it, tells an operator federal law requires
--      something it does not. Where a broker or the company's own policy imposes a cycle, the
--      certificate it issues carries the date, which is what 'ondocument' reads.
--
--   4. IT WAS DUE "once hired", counted in days. 14-90.004(3)(d) ties it to an event, not a
--      date: trained AND tested before the driver operates the applicable vehicle unsupervised.
--      Hiring somebody on Monday and training them by Friday is perfectly compliant; putting
--      them out alone on Tuesday is not.
--
-- What is NOT changed here: the name, and the fact that this rule overlaps PASS_TRAINING and
-- ADA_PROFICIENCY, both of which ask about the same training under the same trigger. That is a
-- question about what to ask drivers, not a question of fact, and it is the operator's to answer.

UPDATE compliancerules
   SET citation = '49 CFR 37.165; 49 CFR 37.173; F.A.C. 14-90.004(3)(d)',
       description = CONCAT(
         'Training to proficiency in securing a mobility device and its occupant, operating the ',
         'lift and other accessibility equipment, and assisting the passengers who use them. No ',
         'regulation names a course, a trainer or a certificate: the employer may train its own ',
         'drivers or buy the training in, and what is required is that the driver can actually do ',
         'it. Evidence is a certificate of completion or the company''s own training and ',
         'proficiency record. In Florida, F.A.C. 14-90.004(3)(d) asks for testing as well as ',
         'training - the driver must be shown to have the skill, not merely to have attended.'),
       -- No regulatory interval. It goes out of date when the evidence itself says it does.
       recurrence = 'ondocument',
       recurrencedays = NULL,
       duedays = NULL,
       duetext = 'Before the driver operates an applicable vehicle unsupervised'
 WHERE code = 'SECUREMENT_TRAINING_CERT';

-- The thing filed against it. Not "a certificate" - the record of the training and the testing,
-- which a certificate is only one form of.
UPDATE credentialtypes
   SET name = 'Passenger assistance and wheelchair securement training',
       description = 'A certificate of completion, or the company''s own record of the training '
                     'given and the proficiency testing passed. Record who provided it.',
       defaultvaliddays = NULL
 WHERE code = 'WHEELCHAIR_SECUREMENT';
