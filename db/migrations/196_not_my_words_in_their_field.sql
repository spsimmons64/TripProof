-- ################################################################################################
-- # 196 - clear the sentence 194 wrote into a field that belongs to the company.
-- #
-- # 194 seeded every account's driving-record election to "every driver" so that nothing changed
-- # under them when the choice appeared, and it filled the reason with "Asked of every driver, as
-- # it was before this was a choice." That is a note about a migration. The field it went into is
-- # "Who asks for it", it shows on the settings page and it prints on the driver's requirement row
-- # in place of the federal citation.
-- #
-- # The election stays. Only the words go, so the field is empty and waiting for the company's own
-- # answer rather than carrying mine.
-- ################################################################################################

UPDATE companyrulepolicy
   SET reason = NULL
 WHERE reason = 'Asked of every driver, as it was before this was a choice.';
