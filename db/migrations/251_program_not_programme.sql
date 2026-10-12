-- "Program", not "programme".
--
-- American spelling throughout, in every word an operator or an auditor reads. The engine is
-- written for US carriers against the CFR, and the CFR says "program" - 49 CFR 382.305 is headed
-- "Random testing", and every reference in Part 382 and Part 40 to what the employer must operate
-- is a "program". A requirements list that spells it the English way beside a citation that does
-- not is the software's accent showing, in a document somebody files with the government.

UPDATE compliancerules
   SET name        = REPLACE(REPLACE(name,        'Programme', 'Program'), 'programme', 'program'),
       description = REPLACE(REPLACE(description, 'Programme', 'Program'), 'programme', 'program'),
       duetext     = REPLACE(REPLACE(duetext,     'Programme', 'Program'), 'programme', 'program'),
       note        = REPLACE(REPLACE(note,        'Programme', 'Program'), 'programme', 'program')
 WHERE description LIKE '%programme%' OR name LIKE '%programme%'
    OR note LIKE '%programme%' OR duetext LIKE '%programme%';
