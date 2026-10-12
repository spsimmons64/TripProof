-- ################################################################################################
-- # 054 - Florida Chapter 14-90 reaches an operation, not a driver.
-- #
-- # Florida's Chapter 14-90 medical examination (FDOT form 725-030-11) is not asked of every driver
-- # in the state: it applies to an operation, and to the vehicles in it, that fall under those bus
-- # transit requirements. A driver's own answers cannot settle that - the company knows whether the
-- # rule reaches it - so this one stops being flat 'required' and becomes a condition the account
-- # answers for itself on its qualification list.
-- #
-- # That is the general shape: a conditional item aimed at 'cdl' or 'noncdl' is decided by what the
-- # driver said, and stays locked; a conditional item aimed at every driver is decided by the
-- # company, and the company may switch it off.
-- ################################################################################################
UPDATE compliancedocs
   SET name       = 'Bus transit medical examination (FDOT 725-030-11)',
       obligation = 'conditional',
       appliesif  = 'The operation, or the vehicle, falls under Florida Chapter 14-90 bus transit requirements',
       -- `renewal` is one short line (80 characters); the rest of the rule lives in `description`.
       renewal    = 'At least every 24 months while it applies',
       description = 'Florida Chapter 14-90 medical examination on FDOT form 725-030-11. Before hire, at '
                     'least every 24 months while it applies, and again before returning to duty after a '
                     'medical absence of 30 days or more.',
       validdays  = 730
 WHERE subject = 'driver' AND code = 'FL_TRANSIT_MEDICAL';

UPDATE accountqualifications
   SET obligation = 'conditional', validdays = 730
 WHERE catalog = 1 AND code = 'FL_TRANSIT_MEDICAL' AND obligation = 'required';

-- The System Safety Program Plan is the same shape. Rule 14-90.004(1) requires a covered bus
-- transit system to have an SSPP, and that plan must address driver selection and training: the
-- system keeps background checks and qualifications, a description of the training each driver was
-- given and completed, and duty-status records, generally for at least four years.
UPDATE compliancedocs
   SET obligation = 'conditional',
       appliesif  = 'The operation, or the vehicle, falls under Florida Chapter 14-90 bus transit requirements',
       renewal    = 'Kept current while driving; records held at least 4 years',
       description = 'Selection and training records the System Safety Program Plan calls for: background '
                     'checks and qualifications, what training each driver was given and completed, and '
                     'duty-status records. Training covers safety and operating procedures, vehicle '
                     'inspection and familiarisation, manoeuvring, boarding and alighting, wheelchair lifts '
                     'and securement, defensive driving, passenger assistance, emergencies and security '
                     'threats, and driving conditions.'
 WHERE subject = 'driver' AND code = 'FL_SSPP_DRIVER_RECORDS';

UPDATE accountqualifications
   SET obligation = 'conditional'
 WHERE catalog = 1 AND code = 'FL_SSPP_DRIVER_RECORDS' AND obligation = 'required';
