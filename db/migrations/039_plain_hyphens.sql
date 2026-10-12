-- ################################################################################################
-- # 039 - hyphens, not em dashes, in everything a person reads.
-- #
-- # A house rule as of 2026-09-23. The source files were fixed in place; these are the rows already
-- # loaded, where the dash sits in text the compliance pages show.
-- ################################################################################################
UPDATE compliancedocs SET
    name        = REPLACE(REPLACE(name, '—', '-'), '–', '-'),
    description = REPLACE(REPLACE(description, '—', '-'), '–', '-'),
    renewal     = REPLACE(REPLACE(renewal, '—', '-'), '–', '-'),
    appliesif   = REPLACE(REPLACE(appliesif, '—', '-'), '–', '-'),
    authority   = REPLACE(REPLACE(authority, '—', '-'), '–', '-')
    WHERE name LIKE '%—%' OR description LIKE '%—%' OR renewal LIKE '%—%'
       OR appliesif LIKE '%—%' OR authority LIKE '%—%'
       OR name LIKE '%–%' OR description LIKE '%–%' OR renewal LIKE '%–%'
       OR appliesif LIKE '%–%' OR authority LIKE '%–%';
