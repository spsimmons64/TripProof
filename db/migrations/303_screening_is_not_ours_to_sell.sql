-- TripProof stops selling background checks.
--
-- The four BACKGROUND_* rows priced a thing this product was never in a position to sell. Under
-- the FCRA the party that obtains a consumer report for employment purposes must be the party
-- evaluating the consumer for employment - and that is the transport company deciding whether to
-- hire the driver, never the software it decides with. Reselling the report would also have made
-- this a consumer reporting agency in its own right, with everything §607 and §611 ask of one.
--
-- So each company holds its own account with backgroundchecks.com, is billed by them directly,
-- signs its own certification, and its own name appears on the disclosure the driver signs. There
-- is nothing left here to price.
--
-- The rows are retired rather than deleted: orders already placed name the tier they were bought
-- under, and a screen reading an old order still has to be able to say what it was.
UPDATE feeschedule SET active = 0, updated = UTC_TIMESTAMP()
 WHERE code LIKE 'BACKGROUND\_%';
