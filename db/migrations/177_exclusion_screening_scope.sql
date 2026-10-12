-- ################################################################################################
-- # 177 - exclusion screening, named for what it is rather than for one statute.
-- #
-- # The row claimed 42 U.S.C. 1396a(a)(87)(A) and 42 CFR 1001.1901 as though every NEMT employer in
-- # the country must run both databases on every driver before hiring. That is not what either
-- # says, and presenting it that way makes the screen wrong in most states.
-- #
-- # What is true: OIG treats the LEIE as the primary way to find OIG exclusions and recommends
-- # screening before hiring and periodically afterwards, because a federal health care program may
-- # not pay for services furnished by an excluded person - which reaches transportation. SAM.gov is
-- # a different list carrying broader federal debarment information, and whether it must be checked
-- # comes from a contract or a programme, not from the exclusion statute.
-- #
-- # So the name says both lists, the authority line says where the obligation comes from, and the
-- # note says which of the two is the exclusion check. When the engine can answer "does SAM apply
-- # to this company", that becomes a condition rather than a sentence.
-- ################################################################################################

UPDATE compliancerules
   SET name = 'Federal Exclusion Screening - OIG LEIE / SAM.gov',
       citation = 'Federal health care program, Medicaid or contract requirement',
       note = 'The LEIE is the exclusion check. SAM.gov is a broader federal debarment list and is '
              'screened where a contract or programme asks for it.'
 WHERE subject = 'driver' AND code = 'EXCLUSION_CHECK_DRIVER' AND effectiveto IS NULL;
