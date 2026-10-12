-- ################################################################################################
-- # 190 - a medical variance is one of two things, so the field offers the two.
-- #
-- # It went in as free text and the first person to meet it asked what belonged in it, which is the
-- # field telling you it is wrong. There are exactly two ways a driver is medically qualified while
-- # not meeting a standard in 391.41:
-- #
-- #   SPE certificate   49 CFR 391.49. A fixed deficit of a limb - a missing or impaired hand, arm,
-- #                     foot or leg. The driver demonstrates to a State examiner that they can
-- #                     operate safely, and the certificate is limited to the kind of vehicle they
-- #                     were evaluated in. A copy belongs in the driver qualification file under
-- #                     391.51(b)(8).
-- #   Exemption         A federal exemption programme - vision, insulin-treated diabetes, hearing,
-- #                     seizure history. Granted by FMCSA for a term, and renewable.
-- #
-- # The kind is a choice; what is left to type is the reference and any limitation on it, which is
-- # the part nobody could have guessed the shape of.
-- ################################################################################################

ALTER TABLE drivermvrs
  ADD COLUMN medvariancetype VARCHAR(12) NULL AFTER medcertexpires;   -- spe | exemption
