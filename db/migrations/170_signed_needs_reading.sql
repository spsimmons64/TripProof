-- ################################################################################################
-- # 170 - a document the driver signed down a link is unread until somebody here reads it.
-- #
-- # The rule has been written down twice already and enforced in one place both times: anything
-- # that arrives from outside this office is unread until a person here says they read it. The gate
-- # was built over `uploadrequests`, so a document the driver SIGNED - which comes back through
-- # `signingrequests`, a different table - went straight to green without anybody opening it.
-- #
-- # It is the same obligation and the same risk. A signature arriving down a link may be on the
-- # wrong document, signed by somebody else at the driver's keyboard, or signed with a name nobody
-- # recognises, and none of that is visible until a person looks.
-- ################################################################################################

ALTER TABLE signingrequests
    ADD COLUMN IF NOT EXISTS reviewedon DATETIME    NULL AFTER signedon,
    ADD COLUMN IF NOT EXISTS reviewedby VARCHAR(36) NULL AFTER reviewedon;

-- Everything signed before this existed has been lived with and is treated as read: putting a
-- fortnight of old signatures into review would be a backlog nobody created.
UPDATE signingrequests SET reviewedon = signedon WHERE signedon IS NOT NULL AND reviewedon IS NULL;
