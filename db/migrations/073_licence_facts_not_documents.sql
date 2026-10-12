-- ################################################################################################
-- # 073 - a licence class is not a document.
-- #
-- # 063 put "Commercial driver's license of the right class" and "CDL passenger (P) endorsement" on
-- # the qualification list, where every row is something the office files a copy of. Neither is: the
-- # document is the copy of the licence, which the list already asks for, and the class and the
-- # endorsement are facts printed on that card.
-- #
-- # Those facts are recorded where they can be used - drivers.licenseclass and drivers.endorsements,
-- # read from the application and from the barcode - and they are enforced where they matter, on the
-- # trip: LICENCE_FITS_VEHICLE asks whether the licence held covers the vehicle driven. Asking an
-- # office to "file" them was asking for a copy of a copy.
-- ################################################################################################
UPDATE compliancedocs SET active = 0
 WHERE subject = 'driver' AND code IN ('CDL_LICENSE', 'CDL_PASSENGER_ENDORSEMENT');

DELETE FROM accountqualifications WHERE code IN ('CDL_LICENSE', 'CDL_PASSENGER_ENDORSEMENT');
