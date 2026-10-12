-- ################################################################################################
-- # 178 - a hired driver is "hired", not "active".
-- #
-- # "Active" is what a record is: present, not deleted, not archived - which is why accounts, users
-- # and credential types all use it for that. A driver who has been taken on is a different idea,
-- # and borrowing the word made the screens say "Active" where the office says "hired", and left
-- # "Pending" looking like its opposite rather than its predecessor.
-- #
-- # The stored value changes with the word, because a status that reads one way and stores another
-- # is how a report ends up disagreeing with the screen it was run from.
-- ################################################################################################

UPDATE drivers SET status = 'hired' WHERE status = 'active';
