-- ################################################################################################
-- # 188 - what the State says about the driver's medical certification.
-- #
-- # A paper medical examiner's certificate in a filing cabinet is not what qualifies a CDL holder.
-- # Under 383.71 the certificate information is supplied electronically to the licensing State,
-- # which carries the medical qualification status on the CDLIS record, and where the two disagree
-- # the electronic record is the one that counts. 391.51(b)(7)(ii) then requires the carrier to
-- # obtain the CDLIS motor vehicle record carrying that information and keep it in the DQ file.
-- #
-- # The hole this closes is specific and it is bad: a driver hands the office a medical card that
-- # looks perfectly valid while the State has already downgraded them, and nothing in TripProof
-- # asks. The card is real. The driver is not certified. Only the State's record says so.
-- #
-- # ONE DOCUMENT, TWO REQUIREMENTS. The CDLIS record is not a second thing to collect - it is the
-- # driving record this office already pulls, read for what else it carries. So the fields go on
-- # the MVR rather than into a new upload, and the new rule reads them. The alternative, a separate
-- # requirement with its own copy of the date, is how a file ends up holding two answers to one
-- # question with nothing to say which is current.
-- ################################################################################################

ALTER TABLE drivermvrs
  ADD COLUMN selfcert       VARCHAR(2)  NULL AFTER finding,   -- NI | EI | NA | EA
  ADD COLUMN medcertstatus  VARCHAR(16) NULL AFTER selfcert,  -- certified | notcertified | notshown
  ADD COLUMN medcertexpires DATE        NULL AFTER medcertstatus,
  ADD COLUMN medvariance    VARCHAR(160) NULL AFTER medcertexpires;

-- ------------------------------------------------------------------------------------------------
-- The requirement.
--
-- Before driving rather than before hiring, with the medical certificate it checks against: a
-- company may take somebody on while the State's record is being sorted out; it may not put them
-- in a commercial vehicle. A hard stop, because a driver the State shows as not certified is not
-- medically qualified whatever paper the office is holding.
--
-- It reaches every interstate CDL holder. Whether they self-certified as excepted, or intrastate,
-- is not something the company knows before it reads the record - it is on the record, and the
-- engine reads it there.
-- ------------------------------------------------------------------------------------------------
INSERT INTO compliancerules (recordid, subject, code, name, authoritytype, authority, citation,
                             applieswhen, evidencekind, evidencesource, origin, reviewrequired,
                             determination, blocking, gate, grouping, duestage, duetext,
                             recurrence, warndays, note, sortorder, effectivefrom)
VALUES (UUID(), 'driver', 'CDL_MEDICAL_STATUS',
        'CDLIS medical certification status', 'regulation', 'FMCSA',
        '49 CFR 391.51(b)(7)(ii); 49 CFR 383.71',
        '{"all":[{"fact":"operation.interstate","is":true},{"fact":"driver.cdl","is":true}]}',
        'query', 'cdlismedical', 'thirdparty', 0, 1, 1, 'hardstop', 'regulatory',
        'predrive', NULL, 'ondocument', 30,
        'Read from the CDLIS driving record, not from the paper certificate. Where the two '
        'disagree the electronically supplied medical information is the one that governs.',
        16, CURRENT_DATE);
