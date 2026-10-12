-- The service agent requirement is answered by a policy, not by a contract.
--
-- It asked for "the consortium or third party administrator agreement" - the paperwork a C/TPA
-- sends when you enrol. That is a receipt. What 49 CFR Part 40 Subpart Q (40.341 to 40.355) and
-- 382.105 actually put on the carrier is harder than holding a receipt: the carrier keeps the
-- responsibility even where a service agent does the work, so it has to be able to say how its
-- testing is administered, who its agents are, what each is authorised to do, how results reach
-- the DER, and what happens when a provider changes.
--
-- An enrolment letter says none of that. A policy does, and the policy is the thing an auditor
-- asks to see - so this becomes the fifth of the policies TripProof publishes and the company
-- adopts, filling itself in from the account and from whoever currently holds the DER and
-- safety appointments.
--
-- The agreement itself is not lost: it is a document, and it goes in the company's files like
-- any other. What changes is that the requirement no longer treats having a receipt as having
-- a programme.

UPDATE compliancerules
   SET name = 'DOT drug and alcohol testing procedures and service agent oversight policy',
       evidencekind = 'policy',
       evidencesource = 'policy:SERVICE_AGENT_POLICY',
       citation = '49 CFR 40.341 - 40.355; 49 CFR 382.105',
       duetext = 'In force while any driver Part 382 covers is employed',
       description = CONCAT(
         'The carrier keeps responsibility for its drug and alcohol testing programme even ',
         'where a consortium, third-party administrator, collection site, laboratory, medical ',
         'review officer or substance abuse professional does the work - 49 CFR Part 40 ',
         'Subpart Q. So the carrier must be able to say how its testing is administered: who ',
         'its service agents are, what each is authorised to do, how results reach the ',
         'designated employer representative, what is done when a driver is prohibited, and ',
         'how records move when a provider changes. An enrolment letter from a consortium ',
         'answers none of that. This policy does, and it names the DER and the safety manager ',
         'from the appointments on file rather than from anything typed into it.')
 WHERE code = 'TPA_AGREEMENT';
