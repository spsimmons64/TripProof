-- The SSPP driver records are the company's to keep, not a document the driver hands in.
--
-- FL_SSPP_DRIVER_RECORDS sat on every Chapter 14-90 driver's list asking them to supply a
-- "Driver selection and training records (SSPP)" document. There is no such thing. FDOT issues
-- no certificate by that name, and nothing in Chapter 14-90 asks a driver for one.
--
-- It also cited 14-90.004(1), which is the requirement to HAVE a System Safety Program Plan -
-- the plan itself, already asked for by the SSPP rule. The driver records obligation is
-- 14-90.004(3)(g), and it is addressed to the bus transit system: keep, for at least four
-- years, the driver background check and qualification records, a detailed description of the
-- training administered to and completed by each driver, and the driver duty status records.
--
-- Every one of those is already held - licences, screenings, training credentials, duty status
-- records. So the rule moves to the company and is answered by looking at them, rather than
-- asking a driver to upload a fourth document that restates the other three.

UPDATE compliancerules
   SET effectiveto = CURDATE(),
       note = 'Retired. 14-90.004(3)(g) is a recordkeeping duty on the transit system, not a '
              'driver document. Replaced by the company rule of the same code family.'
 WHERE code = 'FL_SSPP_DRIVER_RECORDS' AND subject = 'driver';

INSERT INTO compliancerules
  (recordid, accountid, code, name, description, subject, authoritytype, authority, jurisdiction,
   citation, sourceurl, applieswhen, evidencekind, evidencesource, origin, extendable, blocking,
   gate, grouping, duestage, duetext, recurrence, warndays, sensitivity, retentionrule,
   effectivefrom, sortorder)
SELECT UUID(), NULL, 'FL_SSPP_RECORDKEEPING',
       'Driver qualification and training records (SSPP)',
       CONCAT('The records a bus transit system must keep for each driver under its System ',
              'Safety Program Plan: the background check and qualification records, a detailed ',
              'description of the training administered to and completed by the driver, and ',
              'the duty status records. Held at least four years. Nothing is uploaded for this ',
              '- it is answered by the records already on each driver''s file, and it is short ',
              'only where one of them is missing.'),
       'company', 'regulation', 'FDOT', 'FL', 'F.A.C. 14-90.004(3)(g)',
       'https://www.flrules.org/gateway/ruleno.asp?id=14-90.004',
       '{"fact":"company.transit","is":true}',
       'process', 'ssppdriverrecords', 'office', 0, 1,
       'deficiency', 'regulatory', 'ongoing',
       'Kept for every driver, at least four years',
       'once', 30, 'normal',
       'Held 4 years - F.A.C. 14-90.004(3)(g)', '2010-01-01', 69
 WHERE NOT EXISTS (SELECT 1 FROM compliancerules WHERE code = 'FL_SSPP_RECORDKEEPING');
