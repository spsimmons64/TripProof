-- ################################################################################################
-- # 139 - the SPHI response, question by question.
-- #
-- # The inquiry already held two loose answers: "accidents" and "drugalcohol". The form asks far
-- # more precisely than that, and each answer has a different consequence:
-- #
-- #   §391.23(d)  accidents recorded under §390.15, with dates, injuries, fatalities and hazmat
-- #   §391.23(e)  four separate drug and alcohol questions, each Yes / No / no records
-- #   §40.25      the SAP and return-to-duty answers that follow a violation
-- #
-- # Three things the form is careful about, and so is this:
-- #
-- # "No" and "no records available" are different answers. An employer saying there were no
-- # accidents is evidence; an employer saying they cannot tell is a gap the carrier still owns. A
-- # single boolean would flatten the two into the same thing, so every answer here is three-valued
-- # and the SAP answers four-valued, carrying "not applicable" as its own state.
-- #
-- # The drug and alcohol section is NOT asked of an FMCSA employer. That history comes from the
-- # Clearinghouse pre-employment query, and asking the previous employer as well duplicates it. The
-- # section applies to prior employment under another DOT mode, which is why the mode is recorded.
-- #
-- # The certification is the employer's own statement - name, title, company, telephone, email and
-- # a typed signature. It is what turns a filled-in form into a response somebody stands behind.
-- ################################################################################################

ALTER TABLE employerinquiries
    -- Section 3: what the employer confirms about the employment itself.
    ADD COLUMN IF NOT EXISTS employmentverified VARCHAR(10)  NULL AFTER employed,
    ADD COLUMN IF NOT EXISTS position           VARCHAR(120) NULL AFTER employmentverified,
    ADD COLUMN IF NOT EXISTS confirmedfrom      DATE         NULL AFTER position,
    ADD COLUMN IF NOT EXISTS confirmedthrough   DATE         NULL AFTER confirmedfrom,
    ADD COLUMN IF NOT EXISTS operatedcmv        VARCHAR(10)  NULL AFTER confirmedthrough,
    ADD COLUMN IF NOT EXISTS dotmode            VARCHAR(16)  NULL AFTER operatedcmv,

    -- Section 4: §390.15 accident history. `accidentanswer` is no | yes | norecords, and the rows
    -- themselves stay in `accidents`.
    ADD COLUMN IF NOT EXISTS accidentanswer     VARCHAR(10)  NULL AFTER dotmode,
    ADD COLUMN IF NOT EXISTS accidentsattached  TINYINT(1)   NOT NULL DEFAULT 0 AFTER accidentanswer,

    -- Section 5: the four questions, each yes | no | na.
    ADD COLUMN IF NOT EXISTS alcohol04          VARCHAR(4)   NULL AFTER accidentsattached,
    ADD COLUMN IF NOT EXISTS positivetest       VARCHAR(4)   NULL AFTER alcohol04,
    ADD COLUMN IF NOT EXISTS refusedtest        VARCHAR(4)   NULL AFTER positivetest,
    ADD COLUMN IF NOT EXISTS otherviolation     VARCHAR(4)   NULL AFTER refusedtest,

    -- Section 6: SAP and return to duty, each yes | no | unknown | na.
    ADD COLUMN IF NOT EXISTS sapevaluated       VARCHAR(8)   NULL AFTER otherviolation,
    ADD COLUMN IF NOT EXISTS saptreatment       VARCHAR(8)   NULL AFTER sapevaluated,
    ADD COLUMN IF NOT EXISTS rtdtest            VARCHAR(8)   NULL AFTER saptreatment,
    ADD COLUMN IF NOT EXISTS followupplan       VARCHAR(8)   NULL AFTER rtdtest,

    -- Section 7: who certified it.
    ADD COLUMN IF NOT EXISTS certtitle          VARCHAR(120) NULL AFTER respondedby,
    ADD COLUMN IF NOT EXISTS certcompany        VARCHAR(160) NULL AFTER certtitle,
    ADD COLUMN IF NOT EXISTS certphone          VARCHAR(40)  NULL AFTER certcompany,
    ADD COLUMN IF NOT EXISTS certemail          VARCHAR(160) NULL AFTER certphone,
    ADD COLUMN IF NOT EXISTS certsignature      VARCHAR(160) NULL AFTER certemail,

    -- Section 9: the carrier's own review of what came back. Separate from the response, because
    -- one is the employer's statement and the other is what this office decided about it.
    ADD COLUMN IF NOT EXISTS disposition        VARCHAR(24)  NULL AFTER effortnote,
    ADD COLUMN IF NOT EXISTS reviewcomments     TEXT         NULL AFTER disposition,
    ADD COLUMN IF NOT EXISTS reviewedon         DATETIME     NULL AFTER reviewcomments,
    ADD COLUMN IF NOT EXISTS reviewedby         VARCHAR(36)  NULL AFTER reviewedon;
