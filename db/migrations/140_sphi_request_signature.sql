-- ################################################################################################
-- # 140 - the request is signed before it goes out.
-- #
-- # Section 2 of the SPHI is the prospective employer - who is asking. A previous employer is being
-- # asked to release somebody's accident and drug and alcohol history to a stranger, and what makes
-- # that a request rather than a phishing email is that a named person at the carrier put their name
-- # to it.
-- #
-- # So the signature is a precondition of sending, not a field on a form somebody may skip: no
-- # signature, no request. It is recorded once per inquiry and stands for every attempt on it - a
-- # second fax of the same request is the same request, signed by the same person.
-- ################################################################################################

ALTER TABLE employerinquiries
    ADD COLUMN IF NOT EXISTS requestsignature VARCHAR(160) NULL AFTER token,
    ADD COLUMN IF NOT EXISTS requestfontkey   VARCHAR(24)  NULL AFTER requestsignature,
    ADD COLUMN IF NOT EXISTS requestsignedby  VARCHAR(36)  NULL AFTER requestfontkey,
    ADD COLUMN IF NOT EXISTS requestsignedon  DATETIME     NULL AFTER requestsignedby;
