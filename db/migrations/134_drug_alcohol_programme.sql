-- ################################################################################################
-- # 134 - which drug and alcohol programme a driver is under, and which one a bar arises from.
-- #
-- # Everything here was written against 49 CFR Part 382, and `eligibility.covered()` asks one
-- # question: does Part 382 reach this driver? That gets two different things wrong at once.
-- #
-- # A driver Part 382 does NOT reach, but F.A.C. 41-2.006(4)(a) does, tests positive: the result is
-- # filed and nobody is barred, because the code looked for a federal hook and did not find one.
-- # The Florida CTD framework requires removal from safety-sensitive duty just the same.
-- #
-- # And in the other direction: a driver under a CTD or a company programme who tests positive must
-- # not be pushed into the federal process. The DOT return-to-duty process - a DOT-qualified SAP,
-- # 40.305, the Clearinghouse - belongs to DOT-covered drivers. Calling a company's own evaluation
-- # "DOT SAP" would be a false statement about what was done, in a record an auditor reads.
-- #
-- #   dot      49 CFR Part 382        DOT SAP, 40.305 return to duty, Clearinghouse
-- #   ctd      F.A.C. 41-2.006(4)(a)  removal from duty, evaluation, return to duty under the CTD
-- #   broker   a contract says so     whatever that contract requires
-- #   company  the company's own      an employment matter, and recorded as one
-- #
-- # The programme is recorded on the DRIVER, because it is a fact about how they are employed, and
-- # on the PROHIBITION, because a bar has to say under what authority it was imposed - and the
-- # answer must not change later because somebody edited the driver.
-- ################################################################################################

ALTER TABLE drivers
    ADD COLUMN IF NOT EXISTS datprogram VARCHAR(16) NULL AFTER chapter1490;

ALTER TABLE driverprohibitions
    ADD COLUMN IF NOT EXISTS program VARCHAR(16) NULL AFTER source;

-- Everything recorded before this was recorded under the only programme the code knew.
UPDATE driverprohibitions SET program = 'dot' WHERE program IS NULL;
