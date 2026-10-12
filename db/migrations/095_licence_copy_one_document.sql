-- ################################################################################################
-- # 095 - a licence is one document, photographed twice.
-- #
-- # The front and the back are two sides of one card, and the file wants the card - not two loose
-- # images that have to be opened one after the other and read together. So the two photographs
-- # become the pages of a single PDF when they are filed, and the licence carries that one document.
-- ################################################################################################
ALTER TABLE driverlicenses
    ADD COLUMN copydocumentid VARCHAR(36) NULL AFTER note,
    ADD CONSTRAINT fk_driverlicenses_copy FOREIGN KEY (copydocumentid) REFERENCES documents (recordid);

-- Whatever was filed as a front before this stands as the copy until a new one is filed.
UPDATE driverlicenses SET copydocumentid = COALESCE(frontdocumentid, backdocumentid)
 WHERE copydocumentid IS NULL AND (frontdocumentid IS NOT NULL OR backdocumentid IS NOT NULL);

ALTER TABLE driverlicenses
    DROP FOREIGN KEY fk_driverlicenses_front,
    DROP FOREIGN KEY fk_driverlicenses_back,
    DROP COLUMN frontdocumentid,
    DROP COLUMN backdocumentid;
