-- ################################################################################################
-- # 092 - a licence has two sides, and the file needs both.
-- #
-- # What is printed on the back of a licence is not decoration: endorsements, restrictions, the
-- # organ-donor line, and in several states the real expiry of a class that the front only hints
-- # at. An office that files the front alone has filed half the document, and finds out which half
-- # mattered during an audit.
-- ################################################################################################
ALTER TABLE driverlicenses
    ADD COLUMN frontdocumentid VARCHAR(36) NULL AFTER note,
    ADD COLUMN backdocumentid  VARCHAR(36) NULL AFTER frontdocumentid,
    ADD CONSTRAINT fk_driverlicenses_front FOREIGN KEY (frontdocumentid) REFERENCES documents (recordid),
    ADD CONSTRAINT fk_driverlicenses_back FOREIGN KEY (backdocumentid) REFERENCES documents (recordid);
