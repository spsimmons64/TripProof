-- ################################################################################################
-- # 337 - corrections from the rule review packet (2026-10-21).
-- #
-- # Only what is plainly wrong and checked against its source: descriptions copied onto the wrong
-- # rule, due text that contradicts the rule's own timing, a Florida rule reaching other states, and
-- # citations off by a paragraph. Judgement calls - the Florida driver age, the Georgia training
-- # timing, whether a broker's checks are the provider's to file - are left to the reviewer.
-- #
-- # Sources read: 49 CFR 391.51(b) and 391.23 (law.cornell.edu); DCH NEMT Part II (October 2026)
-- # 910.1-910.2, 914.2.1-914.2.4, 915.1.3-915.1.4, 1006.5.4. The Georgia DHS manual (MAN1425) was
-- # not available, so the DHS descriptions say only what each rule's own name and citation say.
-- #
-- # Every rule stays as it is in review - all are drafts - so each is approved by whoever reads it.
-- ################################################################################################

-- --- Descriptions copied from other rules -------------------------------------------------------

UPDATE compliancerules SET description = 'Georgia DHS coordinated transportation requires a fingerprint-based criminal history check of each driver through the Georgia Crime Information Center (GCIC) and the FBI, under DHS MAN1425 Chapter 2 and O.C.G.A. 49-2-14.'
 WHERE code = 'DHS_FINGERPRINT' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET description = 'Georgia Medicaid NEMT: no driver or attendant may have a prior conviction for a sexual crime or a crime of violence (DCH 914.2.2); no driver may have been convicted of driving under the influence in the five years before employment; and anyone convicted of a felony in the last five years drives or attends only after satisfactory review by the broker and DCH (914.2.3). The broker conducts the check and the provider keeps the documentation (1006.5.4).'
 WHERE code = 'GA_NET_BACKGROUND' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET description = 'Georgia DHS coordinated transportation requires a verified negative pre-employment drug test before a driver begins (DHS MAN1425 Chapter 2, Drug and Alcohol Testing). A drug screen on file answers it here; that the result was negative is read from the document by whoever reviews it.'
 WHERE code = 'DHS_PREEMP_DRUG' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET description = 'Georgia DHS coordinated transportation requires drivers to complete general orientation training (DHS MAN1425 Chapter 2, Driver Training).'
 WHERE code = 'DHS_ORIENTATION' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET description = 'Georgia Medicaid NEMT requires every driver to be at least 21 years old (DCH 914.2.1). Read from the date of birth on the driver record; there is nothing to file.'
 WHERE code = 'GA_NET_AGE21' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET description = 'Georgia DHS coordinated transportation requires drivers to be at least 21 years old (DHS MAN1425 Chapter 2, Driver Qualifications). Read from the date of birth on the driver record; there is nothing to file.'
 WHERE code = 'DHS_AGE21' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET description = 'Georgia DHS coordinated transportation requires a certified seven-year motor vehicle record before employment, showing fewer than six points and no suspension in the last five years (DHS MAN1425 Chapter 2). The record on file answers it here; the points and suspension history are read from it by whoever reviews it.'
 WHERE code = 'DHS_MVR' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET description = 'Georgia DHS coordinated transportation requires drivers to be trained to proficiency in securing a mobility device and its occupant, operating the lift and other accessibility equipment, and assisting the passengers who use them (DHS MAN1425 Chapter 2, Driver Training; 49 CFR 37.173). Evidence is a certificate of completion or the company''s own training and proficiency record.'
 WHERE code = 'DHS_SECUREMENT' AND accountid IS NULL AND effectiveto IS NULL;

-- --- Due text that contradicts the rule's own timing ----------------------------------------------

-- DCH 910.1/910.2: inspected twice a year, each no later than six months after the last.
UPDATE compliancerules SET duetext = 'Every six months'
 WHERE code = 'GA_NET_VEHICLE_INSPECTION' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET duetext = 'Every month'
 WHERE code = 'GA_NET_OWNER_EXCLUSION' AND accountid IS NULL AND effectiveto IS NULL;

-- DCH 915.1.3 and 915.1.4 ask that a process be "in place". Nothing in the source renews it yearly.
UPDATE compliancerules SET duetext = 'Kept in place', recurrence = 'once', recurrencedays = NULL
 WHERE code IN ('GA_NET_DRIVER_HISTORY_PROCESS', 'GA_NET_DRUG_LAW_PROCESS')
   AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET duetext = 'Kept in place'
 WHERE code = 'DHS_DRUG_PROGRAM' AND accountid IS NULL AND effectiveto IS NULL;

-- --- A Florida rule reaching other states ---------------------------------------------------------

-- F.A.C. 14-90.004 is Florida's: it reaches a company covered by the Florida bus transit program,
-- not any company with a transit contract anywhere.
UPDATE compliancerules
   SET jurisdiction = 'FL', applieswhen = '{"fact":"company.transit.FL_1490","is":true}'
 WHERE code IN ('SSPP', 'SAFETY_MANAGER') AND accountid IS NULL AND effectiveto IS NULL;

-- --- Citations off by a paragraph -------------------------------------------------------------------

-- 391.51(b)(6)(ii) is the CDLIS medical status; (b)(7) the SPE certificate; (b)(8) the National
-- Registry note.
UPDATE compliancerules SET citation = '49 CFR 391.51(b)(6)(ii); 49 CFR 383.71'
 WHERE code = 'CDL_MEDICAL_STATUS' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules
   SET citation = '49 CFR 391.49; 49 CFR 391.51(b)(7)',
       description = REPLACE(description, '391.51(b)(8)', '391.51(b)(7)')
 WHERE code = 'SPE_CERTIFICATE' AND accountid IS NULL AND effectiveto IS NULL;

-- 42 CFR 424.516 is Medicare enrollment; Medicaid's is Part 455 Subpart E.
UPDATE compliancerules SET citation = '42 CFR 455 Subpart E'
 WHERE code = 'MEDICAID_ENROLLMENT' AND accountid IS NULL AND effectiveto IS NULL;

-- 391.23(g) is the previous employer's duty to answer. Consent is 391.23(f)(1) and 40.321(b), and it
-- covers the drug and alcohol history only - the accident history needs none.
UPDATE compliancerules
   SET citation = '49 CFR 391.23(f)(1); 49 CFR 40.321(b)',
       description = 'The driver''s written consent for previous employers to release their drug and alcohol testing history - violations, return-to-duty and follow-up testing (49 CFR 391.23(e)). Previous employers may not release that history without it (391.23(f)(1); 40.321(b)). The accident history under 391.23(d) needs no consent.'
 WHERE code = 'SAFETY_PERFORMANCE_CONSENT' AND accountid IS NULL AND effectiveto IS NULL;
