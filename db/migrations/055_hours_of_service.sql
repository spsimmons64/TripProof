-- ################################################################################################
-- # 055 - the hours of service record is Chapter 14-90's, not every Florida driver's.
-- #
-- # The 12-hour driving / 16-hour duty limits come from F.A.C. 14-90.006 and reach drivers of a
-- # covered bus transit system. They are not a blanket rule on every NEMT driver in the state, so
-- # this stops being flat 'required' and joins the other Chapter 14-90 items as conditional.
-- #
-- # The record itself is the duty-status record the covered system must keep: days worked, hours on
-- # duty, hours driving, and the times reported on and off duty each day, held at least four years.
-- ################################################################################################
UPDATE compliancedocs
   SET obligation    = 'conditional',
       appliesif     = 'The operation, or the vehicle, falls under Florida Chapter 14-90 bus transit requirements',
       legalcitation = 'F.A.C. 14-90.006',
       renewal       = 'Kept daily while driving; records held at least 4 years',
       description   = 'Duty-status record: days worked, hours on duty, hours driving, and the times the '
                       'driver reported on and off duty each day. The limits are 12 hours driving in any '
                       '24, no driving once 16 hours on duty in 24 have been reached, at least 8 '
                       'consecutive hours off before driving again, and at most 72 hours on duty in 7 '
                       'consecutive days followed by at least 24 consecutive hours off.'
 WHERE subject = 'driver' AND code = 'FL_HOURS_OF_SERVICE';

UPDATE accountqualifications
   SET obligation = 'conditional'
 WHERE catalog = 1 AND code = 'FL_HOURS_OF_SERVICE' AND obligation = 'required';
