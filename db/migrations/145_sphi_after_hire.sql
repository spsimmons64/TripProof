-- ################################################################################################
-- # 145 - the safety performance investigation is owed after hiring, not before it.
-- #
-- # 49 CFR 391.23(d) gives the carrier 30 days from the start of employment to complete the
-- # investigation. It cannot be a condition of hiring, because it depends on previous employers
-- # answering - people with no stake in answering, who may take weeks or never reply at all. A
-- # requirement that waits on a stranger is not a requirement the applicant can satisfy.
-- #
-- # The CONSENT stays before hire: 391.23(g) needs the driver's written authorisation before
-- # anybody can be asked, and that is entirely within the applicant's gift. So the asking can begin
-- # before hire and usually should; what moves is when the answer is owed.
-- ################################################################################################

UPDATE compliancerules
   SET duestage = 'athire',
       note = 'Complete within 30 days of the start of employment - 49 CFR 391.23(d)'
 WHERE code = 'SAFETY_PERFORMANCE_HISTORY' AND subject = 'driver';
