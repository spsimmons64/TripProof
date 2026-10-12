-- ################################################################################################
-- # 138 - the safety performance requirement reads the inquiries.
-- #
-- # It pointed at `credential:SAFETY_PERFORMANCE`, so it was answered by somebody filing a document
-- # called that. But 391.23 is not answered by a document - it is answered employer by employer,
-- # and under 391.23(i) an employer who never replies is answered by the record of having asked.
-- #
-- # Pointed at a credential, a driver with three previous employers and one reply read as complete.
-- ################################################################################################

UPDATE compliancerules
   SET evidencesource = 'employerhistory'
 WHERE code = 'SAFETY_PERFORMANCE_HISTORY' AND subject = 'driver';
