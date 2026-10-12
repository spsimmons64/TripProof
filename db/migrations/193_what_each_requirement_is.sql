-- ################################################################################################
-- # 193 - what each requirement actually is, in a sentence or two.
-- #
-- # The list gives a name and a citation. Between them they tell somebody who already knows the
-- # regulations which rule this is, and tell somebody who does not almost nothing. "49 CFR 382.701(a)"
-- # is an address, not an explanation.
-- #
-- # So every rule carries a short description of what it is and why it is asked, written for the
-- # person working the file rather than for the auditor reading it afterwards. It goes at the top
-- # of the requirement's own dialog, which is where somebody has stopped to deal with that one
-- # thing and is the only moment they will read it.
-- #
-- # `note` already exists and is a different job: it is the caveat, the thing that would be
-- # misread without it - "this does not replace the driver's electronic consent". The description
-- # is the plain answer to "what is this". A rule may want both.
-- ################################################################################################

ALTER TABLE compliancerules ADD COLUMN description VARCHAR(600) NULL AFTER name;

UPDATE compliancerules SET description = CASE code

  WHEN 'EMPLOYMENT_APPLICATION' THEN
    'The driver''s own written application for the job, signed by them. It asks for three years of '
    'addresses, every licence held, and - for a commercial driver - ten years of employment '
    'history, so that the company can go and check it. Everything else in this file is built on '
    'what the driver stated here.'

  WHEN 'DRIVER_LICENSE_COPY' THEN
    'A copy of the licence itself, filed so that anybody reading this file can see the class, the '
    'endorsements and the expiry without taking somebody''s word for it.'

  WHEN 'MVR_PREEMPLOYMENT' THEN
    'A driving record from every State the driver has held a licence in, obtained before they are '
    'taken on. It is how the company finds out about convictions, suspensions and crashes that the '
    'driver did not mention on their application.'

  WHEN 'MVR_ANNUAL' THEN
    'Once every twelve months the company obtains a fresh driving record and somebody qualified '
    'reads it, decides whether the driver is still qualified, and signs a note saying so. The '
    'record on its own is not the requirement - the reading and the determination are.'

  WHEN 'CDL_MEDICAL_STATUS' THEN
    'What the licensing State holds about this driver''s medical qualification, read off the CDLIS '
    'driving record rather than off the paper certificate. The examiner sends the result to FMCSA, '
    'FMCSA sends it to the State, and the State''s record is what governs - a driver can hold a '
    'valid-looking certificate while the State has already downgraded them.'

  WHEN 'MEDICAL_CERT' THEN
    'The certificate from a medical examiner on FMCSA''s national registry saying this driver is '
    'physically qualified to operate a commercial motor vehicle. Usually good for two years, less '
    'where the examiner found something that needs watching.'

  WHEN 'FL_TRANSIT_MEDICAL' THEN
    'Florida''s own medical examination for drivers of covered buses, on form FDOT 725-030-11. '
    'Where the system has adopted qualifying alternative standards one physical can answer both '
    'this and the federal certificate.'

  WHEN 'ROAD_TEST' THEN
    'An examiner watches the driver actually operate the kind of vehicle they will be driving - '
    'inspection, coupling, backing, turns, braking, traffic - and certifies the result. A valid '
    'commercial licence of the right class can be accepted instead for some vehicles.'

  WHEN 'LICENCE_ENDORSEMENTS' THEN
    'Whether the licence this driver holds carries the endorsements the vehicle they will operate '
    'requires - a P for carrying passengers, an S for a school bus, an H for hazardous materials. '
    'An endorsement cannot be filed here; it is obtained from the licensing State.'

  WHEN 'SAFETY_PERFORMANCE_CONSENT' THEN
    'The driver''s written permission for this company to ask their previous employers about their '
    'safety performance. Without it those employers may not answer.'

  WHEN 'SAFETY_PERFORMANCE_HISTORY' THEN
    'The company must ask every DOT-regulated employer the driver worked for in the past three '
    'years about their accident history and, where applicable, their drug and alcohol record. What '
    'is required is a good-faith effort to ask - an employer who never replies does not stop the '
    'file being complete, provided the asking is documented.'

  WHEN 'PREEMPLOYMENT_DRUG_TEST' THEN
    'A controlled substances test with a verified negative result before the driver performs any '
    'safety-sensitive function. Not before hire - before driving. A company may take somebody on '
    'contingent on the result.'

  WHEN 'CLEARINGHOUSE_PREEMP' THEN
    'A full query of the FMCSA Drug and Alcohol Clearinghouse before the driver performs any '
    'safety-sensitive function. It needs the driver''s own electronic consent inside the '
    'Clearinghouse. A query coming back "prohibited" is a federal bar, not a paperwork problem.'

  WHEN 'CLEARINGHOUSE' THEN
    'A Clearinghouse query at least once every twelve months for as long as the driver works here. '
    'The pre-employment full query counts as that year''s query, so the clock starts from it.'

  WHEN 'CLEARINGHOUSE_CONSENT' THEN
    'The driver''s general written consent for this company to run limited Clearinghouse queries - '
    'the annual one and any others - without asking them each time.'

  WHEN 'PREEMP_DA_QUESTIONNAIRE' THEN
    'A question put to the applicant: in the past two years, did you test positive or refuse a test '
    'at an employer you applied to but did not work for? Those results are not in the Clearinghouse '
    'and no previous employer will report them, so the only way to find out is to ask.'

  WHEN 'PRIOR_VIOLATION_RTD' THEN
    'Where the driver answered yes to that question, they may not perform safety-sensitive '
    'functions until the return-to-duty process is documented as complete. A negative test taken '
    'here does not answer it - the SAP''s determination and the return-to-duty result do.'

  WHEN 'DA_POLICY_RECEIPT' THEN
    'The driver''s signed receipt for the company''s drug and alcohol policy. It proves they were '
    'given the rules before they were tested under them.'

  WHEN 'RANDOM_TESTING_RECORDS' THEN
    'The driver is in the company''s random testing pool and the records show it. Random testing is '
    'a program obligation rather than an event - what is kept is proof of membership and of the '
    'selections made.'

  WHEN 'DQ_FILE' THEN
    'The file itself. Everything the regulations require about one driver, kept together, for as '
    'long as they work here and three years afterwards.'

  WHEN 'FCRA_FORMS' THEN
    'Where the company buys a background report from a consumer reporting agency, the driver must '
    'first be given a standalone written disclosure and must authorise it in writing. The '
    'disclosure may not be buried in the application.'

  WHEN 'PHI_CONFIDENTIALITY' THEN
    'The driver''s acknowledgment that they will keep passengers'' health information confidential. '
    'A company policy document rather than something HIPAA names, and it is how a company shows it '
    'trained and bound the people who see that information.'

  WHEN 'I9' THEN
    'Proof that this person may legally work in the United States. Section 1 by the first day of '
    'work, Section 2 within three business days of it.'

  WHEN 'W4' THEN
    'The driver''s withholding certificate, so the company can work out what to deduct. An '
    'employment record rather than a safety one.'

  WHEN 'HIPAA_TRAINING_DRIVER' THEN
    'Training in handling protected health information, for a driver working for a HIPAA covered '
    'entity or its business associate.'

  WHEN 'PASS_TRAINING' THEN
    'Training in assisting passengers with disabilities and in using the vehicle''s accessibility '
    'equipment. The driver must be able to do it, not merely have been shown it.'

  WHEN 'SECUREMENT_TRAINING_CERT' THEN
    'Training in securing a wheelchair and its occupant properly. Four tie-downs and a separate '
    'occupant restraint, every time.'

  WHEN 'BBP_TRAINING' THEN
    'Bloodborne pathogens training, where the driver''s duties make contact with blood or other '
    'infectious material reasonably foreseeable.'

  WHEN 'EXCLUSION_OIG_LEIE' THEN
    'A check of the HHS Office of Inspector General''s List of Excluded Individuals and Entities. A '
    'federal health care program may not pay for anything furnished by an excluded person, which '
    'reaches the driver of a Medicaid-funded trip.'

  WHEN 'EXCLUSION_SAM_GOV' THEN
    'A check of the government-wide exclusions list at SAM.gov. Screened because a federal '
    'contract, grant or program asks for it rather than because of the exclusion statute itself.'

  WHEN 'FL_LEVEL1_DRIVER' THEN
    'Florida Level 1 screening - a name-based criminal history check through the State, required of '
    'people working with Medicaid recipients.'

  WHEN 'FL_LEVEL2_DRIVER' THEN
    'Level 2 screening - fingerprint-based, through FDLE and the FBI. Not required of NEMT drivers '
    'by the Medicaid statute itself; it appears here because a contract asks for it.'

  WHEN 'FL_LICENSE_STATUS_NOTICE' THEN
    'The driver''s written acknowledgment that they must tell the company at once if their licence '
    'is suspended, revoked or cancelled.'

  WHEN 'FL_HOURS_OF_SERVICE' THEN
    'Florida''s own limits for covered bus operations - no more than twelve hours driving and '
    'sixteen hours on duty - and the records that show they were kept.'

  WHEN 'FL_SSPP_DRIVER_RECORDS' THEN
    'The driver selection and training records Florida''s System Safety Program Plan requires a '
    'covered operator to keep.'

  WHEN 'FL_TD_DRUG_TESTING' THEN
    'Drug and alcohol testing records for safety-sensitive staff of an operator working under a '
    'Transportation Disadvantaged contract.'

  WHEN 'FL_INTRASTATE_382' THEN
    'Florida applies the federal drug and alcohol testing rules to intrastate commercial drivers of '
    'lighter vehicles, so the testing program reaches this driver even though Part 382 on its own '
    'would not.'

  WHEN 'FL_INTRASTATE_FULL' THEN
    'Florida adopts the federal motor carrier safety regulations for intrastate operation of '
    'vehicles rated 26,001 lb or more, so the whole of Part 391 reaches this driver.'

  ELSE description END
WHERE subject = 'driver' AND effectiveto IS NULL;
