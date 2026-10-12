-- The random testing programme is a programme, not a certificate.
--
-- The requirement asked for `credential:RANDOM_TESTING_PROGRAM` - a file to upload. But what
-- 49 CFR 382.305 puts on the carrier is not a document: it is who is in the pool, how names
-- come out of it, how often, who is told, and what happens to a driver who is selected. The
-- enrolment letter a consortium sends proves none of that, which the rule's own text already
-- said - "a programme with no selection drawn from it in the last twelve months is an
-- enrolment, not a testing programme".
--
-- So it becomes the sixth published policy: TripProof writes the words, the company adopts it
-- with an effective date, and it names the DER and the USDOT number from the record rather
-- than from anything typed into it.
--
-- What does NOT change is the screen. The requirement still opens on the pool, the annual
-- rates and the draws, because that is the work; the policy sits behind a button on it. And
-- the no-draws check moved in app/rules.py so it still applies: adopted and never drawn from
-- reads as nodraws, exactly as filed and never drawn from did.

UPDATE compliancerules
   SET evidencekind = 'policy',
       evidencesource = 'policy:RANDOM_TESTING_POLICY',
       citation = '49 CFR 382.305; 49 CFR 382.401; 49 CFR 382.601'
 WHERE code = 'RANDOM_TESTING_PROGRAM';
