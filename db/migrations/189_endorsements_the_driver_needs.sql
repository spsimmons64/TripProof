-- ################################################################################################
-- # 189 - the endorsements the work needs, against the ones the driver holds.
-- #
-- # TripProof has always recorded what a driver HAS - class, endorsements, read off their licence.
-- # It has never recorded what the work they are being qualified for REQUIRES, so there has been
-- # nothing to compare. A driver with a Class C licence and no endorsements looks perfectly in
-- # order right up until somebody puts them in a sixteen-seat bus, which needs a P.
-- #
-- # Stated rather than read off the fleet, for the same reason the CMV and CDL ticks beside it are
-- # stated: a company buying a bus next quarter has to be able to qualify drivers for it now, and
-- # buying one must not silently disqualify everybody already on the roster. It is a statement
-- # about what this person is being taken on to do.
-- #
-- # This is also where entry-level driver training belongs, and it is why ELDT is NOT a requirement
-- # row of its own. Part 380 Subpart F does not ask the carrier to hold a certificate: it stops the
-- # STATE issuing a first CDL, an upgrade, or a first P, S or H endorsement until a registered
-- # provider has reported the training to FMCSA's Training Provider Registry. So it is not a
-- # document this office collects - it is part of what obtaining the missing endorsement involves,
-- # and the only place it is worth saying so is beside the endorsement that is missing.
-- ################################################################################################

ALTER TABLE drivers ADD COLUMN endorsementsneeded VARCHAR(16) NULL AFTER endorsements;

INSERT INTO compliancerules (recordid, subject, code, name, authoritytype, authority, citation,
                             applieswhen, evidencekind, evidencesource, origin, reviewrequired,
                             determination, blocking, gate, grouping, duestage, duetext,
                             recurrence, warndays, note, sortorder, effectivefrom)
VALUES (UUID(), 'driver', 'LICENCE_ENDORSEMENTS',
        'Endorsements for the vehicle this driver will operate', 'regulation', 'FMCSA',
        '49 CFR 383.93', '{"fact":"driver.needsendorsements","is":true}',
        'document', 'licencematch', 'office', 0, 1, 1, 'hardstop', 'regulatory',
        'predrive', NULL, 'once', 30,
        'An endorsement the driver does not hold cannot be filed - it has to be obtained from the '
        'licensing State, and a first P, S or H endorsement requires entry-level driver training '
        'from a provider on FMCSA''s Training Provider Registry before the State will test for it.',
        13, CURRENT_DATE);
