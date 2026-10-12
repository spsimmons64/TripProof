-- Give the statement one name.
--
-- The signed sheet printed PREV7_ONDUTY as its heading, because the title map that renders a
-- filed document had no line for this doctype and falls back to the code. That map is one of
-- four places the same document is named - the rule, the signature catalogue, the signing
-- catalogue and the sheet - and a document whose name differs between the requirements list and
-- the paper in the file is a document an auditor has to work out is the same thing.
--
-- All four now read exactly this.

UPDATE compliancerules
   SET name = 'Previous 7 Days'' On-Duty Hours Statement'
 WHERE code = 'PREV7_ONDUTY';
