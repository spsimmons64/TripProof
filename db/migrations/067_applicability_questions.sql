-- ################################################################################################
-- # 067 - the questions that decide which conditional requirements reach a company.
-- #
-- # Most of the catalog is conditional, and the conditions divide in two. Some are about the driver
-- # - whether they will operate a commercial motor vehicle - and their own application answers
-- # those. The rest are about the operation: whose money pays for the trips, which programme the
-- # company runs under, whether it obtains background reports through an agency. Nobody but the
-- # company knows those, and until it is asked, a requirement that may not reach it at all was being
-- # shown to every driver as required.
-- #
-- # Each question is asked once, in the company's settings. An item that names a question is asked
-- # of drivers only when the answer is yes; when the answer is no it is not asked at all; and while
-- # the question is unanswered the item is shown but never counted or blocked, so nothing disappears
-- # before anyone has said anything.
-- ################################################################################################
INSERT IGNORE INTO compliancetriggers (code, question, help, sortorder) VALUES
 ('CHAPTER_14_90', 'Operates under Florida Chapter 14-90 bus transit rules',
  'A covered bus transit system, or a vehicle in one. Turns on the bus transit medical examination, '
  'the driver selection and training records, the duty status record and the licence suspension '
  'acknowledgement.', 20),
 ('CTC_TD', 'Operates under a Community Transportation Coordinator',
  'Florida''s Transportation Disadvantaged programme, chapter 427. Turns on the drug and alcohol '
  'testing records that programme requires.', 30),
 ('AHCA_SCREENING', 'Drivers are screened under a Florida programme that requires Level 2',
  'An AHCA-licensed provider whose duties reach s. 408.809, a Department of Elder Affairs programme '
  'under s. 430.0402, or a contract that requires it. Turns on Level 2 fingerprint screening.', 40),
 ('CRA_REPORTS', 'Background reports are obtained from a consumer reporting agency',
  'A third party runs the checks rather than the company looking at public records itself. Turns on '
  'the FCRA disclosure and authorisation.', 50),
 ('HIPAA_COVERED', 'The company is a HIPAA covered entity or a business associate',
  'Decided by its agreements with plans, providers or brokers and by how it handles protected health '
  'information. Turns on HIPAA training and the PHI confidentiality acknowledgment.', 60),
 ('WHEELCHAIR_SERVICE', 'Drivers carry passengers in wheelchairs or work accessible equipment',
  'Turns on wheelchair securement training and the ADA passenger assistance proficiency training.', 70),
 ('EXPOSURE_DUTIES', 'Driver duties make contact with blood or infectious materials foreseeable',
  'OSHA''s standard reaches an employee with occupational exposure. Carrying a passenger to an '
  'appointment does not by itself; particular assistance duties can. Turns on bloodborne pathogens '
  'training.', 80);

UPDATE compliancedocs SET triggercode = CASE code
    WHEN 'FL_TRANSIT_MEDICAL'       THEN 'CHAPTER_14_90'
    WHEN 'FL_SSPP_DRIVER_RECORDS'   THEN 'CHAPTER_14_90'
    WHEN 'FL_HOURS_OF_SERVICE'      THEN 'CHAPTER_14_90'
    WHEN 'FL_LICENSE_STATUS_NOTICE' THEN 'CHAPTER_14_90'
    WHEN 'FL_TD_DRUG_TESTING'       THEN 'CTC_TD'
    WHEN 'FL_LEVEL2_DRIVER'         THEN 'AHCA_SCREENING'
    WHEN 'FCRA_FORMS'               THEN 'CRA_REPORTS'
    WHEN 'HIPAA_TRAINING_DRIVER'    THEN 'HIPAA_COVERED'
    WHEN 'PHI_CONFIDENTIALITY'      THEN 'HIPAA_COVERED'
    WHEN 'SECUREMENT_TRAINING_CERT' THEN 'WHEELCHAIR_SERVICE'
    WHEN 'PASS_TRAINING'            THEN 'WHEELCHAIR_SERVICE'
    WHEN 'BBP_TRAINING'             THEN 'EXPOSURE_DUTIES'
    ELSE triggercode END
WHERE subject = 'driver';
