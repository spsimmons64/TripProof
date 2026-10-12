-- ################################################################################################
-- # 127 - room to write the restriction out.
-- #
-- # "Other restriction" was sized for a phrase. An examiner writing a real one is describing a
-- # condition of driving - when it applies, what it limits, what it depends on - and a field that
-- # cuts it off mid sentence is worse than one that was never filled in, because it reads as
-- # complete. The field is a textarea now, so the column holds what fits in it.
-- ################################################################################################

ALTER TABLE transitmedicals
    MODIFY COLUMN otherrestriction VARCHAR(2000) NULL;
