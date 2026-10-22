###################################################################################################
# Deciding which rules reach somebody, and where each one stands.
#
# Two steps, kept apart on purpose:
#
#   applies()   does this rule reach this driver at all? Answered from facts alone - no documents,
#               no dates, no evidence. A rule that does not reach them is not a thing they are
#               missing, it is a thing that was never asked of them.
#   stand()     given that it reaches them, what have they got? Answered from the records that
#               already exist, which are never copied here.
#
# THREE-VALUED THROUGHOUT. Every answer is True, False or None, and None means "nobody has said".
# It is not False and must never quietly become False: the difference between "this company does
# not drive across state lines" and "nobody has answered that question" is the difference between
# a driver who is qualified and a driver nobody has checked. So `all` with an unknown inside is
# unknown unless something else already made it false, and a rule whose applicability is unknown
# is reported as unknown rather than dropped.
###################################################################################################
import json
from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy.engine import Connection

from app import employers, mvr as mvrs, payerlines, validity
from app.facts import UNANSWERED
from app.recurrence import renewed
from app.db import row, rows

# ------------------------------------------------------------------------------------------------
# The expression language. Deliberately tiny - it has to be readable in a table cell by somebody
# checking whether the rule says what the statute says.
#
#   {"all": [...]}  {"any": [...]}  {"not": {...}}
#   {"fact": "fleet.cmv_federal", "is": true}
#   {"fact": "company.state", "eq": "FL"}
#   {"fact": "fleet.heaviest_gvwr", "lt": 26001}     also gt, lte, gte
#   {"fact": "driver.licenseclass", "in": ["A", "B", "C"]}
# ------------------------------------------------------------------------------------------------


def condition(raw) -> dict | None:
    """The stored expression as a dict.

    MariaDB hands a JSON column back as text through PyMySQL, so a rule read straight from the
    table arrives as a string and every `expr["all"]` blows up on it. Parsed in one place rather
    than at each call site, and a malformed expression is treated as unknown rather than as "no
    condition" - a rule nobody can read must not silently reach everybody."""
    if raw is None or isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {"fact": "__unreadable__"}
    return parsed if isinstance(parsed, dict) else {"fact": "__unreadable__"}


def applies(expr: dict | None, facts: dict) -> bool | None:
    """Whether a rule reaches somebody. None where a fact it needs has not been answered."""
    if not expr:
        return True                      # no condition at all - it reaches everybody

    if "all" in expr:
        seen = [applies(e, facts) for e in expr["all"]]
        if any(v is False for v in seen):
            return False                 # one definite no settles it, unknowns or not
        return None if any(v is None for v in seen) else True
    if "any" in expr:
        seen = [applies(e, facts) for e in expr["any"]]
        if any(v is True for v in seen):
            return True
        return None if any(v is None for v in seen) else False
    if "not" in expr:
        inner = applies(expr["not"], facts)
        return None if inner is None else not inner

    name = expr.get("fact")
    if name not in facts:
        return None
    value = facts[name]
    if value is None:
        return None

    if "is" in expr:
        return bool(value) is bool(expr["is"])
    if "eq" in expr:
        return value == expr["eq"]
    if "in" in expr:
        return value in expr["in"]
    if "has" in expr:                    # the fact is a list, and holds this value
        return expr["has"] in (value or [])
    for op, test in (("lt", lambda a, b: a < b), ("lte", lambda a, b: a <= b),
                     ("gt", lambda a, b: a > b), ("gte", lambda a, b: a >= b)):
        if op in expr:
            try:
                return test(value, expr[op])
            except TypeError:
                return None
    return None


# What a fact is called when a rule says why it does not reach somebody.
FACT_LABELS = {
    "company.medicaid": "Medicaid trips", "company.samgov": "SAM.gov screening required",
    "company.hipaa": "HIPAA covered", "company.transit": "transit contract",
    "company.exposure": "exposure duties", "company.state": "company state",
    "company.operatingstates": "operating states", "operation.interstate": "interstate operation",
    "driver.cmv": "operates a commercial motor vehicle", "driver.cdl": "operates a CDL vehicle",
    "driver.heavy": "operates 26,001 lb or more", "driver.chapter1490": "Chapter 14-90 operation",
    "driver.employee": "employee", "fleet.wheelchair": "wheelchair vehicles in the fleet",
    "fleet.cmv_federal": "FMCSA-covered vehicles in the fleet",
    "reach.part391interstate": "Part 391 reached by interstate operation",
}


def explain_false(expr: dict | None, facts: dict) -> list[str]:
    """The facts that made a rule not apply, said plainly - "Medicaid trips: No"."""
    if not expr:
        return []
    if "all" in expr:
        return [x for e in expr["all"] if applies(e, facts) is False for x in explain_false(e, facts)]
    if "any" in expr:
        return [x for e in expr["any"] for x in explain_false(e, facts)]
    if "not" in expr:
        name = (expr["not"] or {}).get("fact")
        return [f"{FACT_LABELS.get(name, name)}: Yes"] if name else []
    name = expr.get("fact")
    if not name:
        return []
    value = facts.get(name)
    shown = ("Yes" if value else "No") if isinstance(value, bool) else (
        ", ".join(value) if isinstance(value, list) else str(value) if value is not None else "-")
    return [f"{FACT_LABELS.get(name, name)}: {shown or 'none'}"]


def unanswered(expr: dict | None, facts: dict) -> list[str]:
    """Which facts an unknown answer is waiting on, so the page can say what to go and do."""
    if not expr:
        return []
    for key in ("all", "any"):
        if key in expr:
            return [f for e in expr[key] for f in unanswered(e, facts)]
    if "not" in expr:
        return unanswered(expr["not"], facts)
    name = expr.get("fact")
    return [name] if name and facts.get(name) is None else []


# ------------------------------------------------------------------------------------------------
# Finding the evidence.
#
# `evidencesource` on the rule says where to look, as "<kind>" or "<kind>:<which>". The kinds are
# code because there are only a handful of shapes a record can have; the `which` is data, so a new
# rule about a new report is a row and not a patch.
#
# Nothing here copies a record. It reads the one that already exists and reports what it says - so
# a report's state lives in driverreports and nowhere else, which is the bug we kept hitting when
# the same fact was written down twice.
# ------------------------------------------------------------------------------------------------
# Where one rule is answered by another's evidence, what the file should say about it.
ANSWERED_BY = {
    "credential:DOT_MEDICAL_CARD": "Answered by the medical certificate held for the federal "
                                   "requirement.",
    "licensecopy": "Answered by the commercial license on file, in place of a road test "
                   "(49 CFR 391.33).",
    "credential:WHEELCHAIR_SECUREMENT": "Answered by the combined passenger assistance and "
                                        "securement certificate.",
}

PROVING = ("qualified", "clear", "negative", "reviewed", "certified", "excepted", "endorsed",
           "running", "withinlimits", "registerkept", "numbered",
           "paperstands", "adopted", "filed", "registered", "trained", "inspected",
           # 1910.1030(c)(2) is answered either way: a determination that these duties involve
           # no exposure is the determination the section asks for, not a failure to make one.
           "exposed", "noexposure")
# Not an answer: the record exists and does not settle the question. Work for this office rather
# than a verdict on the driver.
REVIEWING = ("review", "notshown", "residenceunknown")
# "prohibited" is the FMCSA Clearinghouse's own word for it, kept rather than translated into one
# of the others: an auditor reading this file should see the word the query returned.
FAILING = ("disqualified", "flagged", "positive", "refusal", "adulterated", "substituted",
           "prohibited", "notcertified", "conflict", "missing", "notage21", "notage18", "notenglish",
           "notgeorgia", "testsowed",
           "notregistered", "noqueryplan", "shorttraining", "opendefect",
           "nodraws", "hoursexceeded", "registershort", "noauthority",
           "nolicense", "licenseinactive", "wrongclass", "newermvr", "removal",
           "awaitingretraining", "inexperienced")

# What a determination MEANS, where "the record came back <word>" would not say it. Only the ones
# that need their own sentence are here; everything else reads perfectly well as the word itself.
SAYS = {
    "nolicense": "No license is on file for this driver. 49 CFR 391.11(b)(5): a driver is not "
                 "qualified unless they hold a currently valid license for the vehicle they "
                 "operate, and nothing here says they hold one.",
    "licenseinactive": "The only license on file for this driver has been marked not active. A "
                       "license that is no longer held does not qualify anybody to drive "
                       "(49 CFR 391.11(b)(5)).",
    "wrongclass": "The license on file is not of a class that permits the work this driver is "
                  "assigned. 49 CFR 391.11(b)(5) asks for a license valid for the VEHICLE "
                  "OPERATED, so a license that is current but of the wrong class qualifies "
                  "nobody - see 49 CFR 383.91 for what each class covers.",
    "untested": "The proficiency testing has not been recorded. F.A.C. 14-90.004(3)(d) asks for "
                "training AND testing demonstrating adequate skills before the driver operates "
                "the applicable vehicle unsupervised - attending the training is not the same as "
                "being shown to have the skill.",
    "opendefect": "A defect reported on this vehicle has not been corrected and certified. 49 CFR "
                  "396.11(c): it must not be dispatched until it is put right, and a clean report "
                  "filed afterwards does not lift it.",
    "shorttraining": "A supervisor's training on file is short of what 49 CFR 382.603 requires - "
                     "at least sixty minutes on alcohol misuse AND at least sixty minutes on "
                     "controlled substances, for each person who may determine reasonable "
                     "suspicion.",
    "nodraws": "A random testing programme is on file, but no selection has been drawn from it "
               "in the last twelve months. 49 CFR 382.305 is a rate to be met across the year, "
               "not an enrolment to be held - a pool nobody draws from tests nobody.",
    "prohibited": "This driver is removed from safety-sensitive functions and may not drive - "
                  "49 CFR 382.501. The bar stands until the whole return-to-duty process in "
                  "49 CFR Part 40 Subpart O is finished: a substance abuse professional "
                  "evaluates them, they complete what the SAP prescribes, the SAP says so, and "
                  "a return-to-duty test comes back negative. Nothing else lifts it.",
    "notregistered": "This company is recorded as NOT registered with the FMCSA Clearinghouse. "
                     "The pre-employment and annual queries its CDL drivers need cannot be run, "
                     "and violations cannot be reported.",
    "noqueryplan": "Registered, but no query plan is recorded. A plan must be bought before any "
                   "query can be run, so the registration cannot yet do what it is for.",
    "notcertified": "The State does not show this driver as certified. Since 30 January 2015 a "
                    "non-excepted interstate CDL holder whose record carries no medical "
                    "certification status is designated not-certified. The certificate in this "
                    "file does not override it - 49 CFR 383.71, 391.51(b)(7)(ii).",
    "conflict": "The medical certificate on file and the State's record give different expiry "
                "dates. The electronically supplied medical information governs.",
    "excepted": "Self-certified as excepted or intrastate, so the State does not carry medical "
                "status. The certificate on file governs.",
    "notshown": "The driving record does not carry medical certification information. Obtain the "
                "CDLIS record from the licensing State.",
    "notage21": "This driver is under 21. 49 CFR 391.11(b)(1) does not permit them to operate a "
                "commercial motor vehicle in interstate commerce, and nothing can be filed that "
                "changes it.",
    "notgeorgia": "Georgia Medicaid accepts a Georgia license, or a license from the bordering state "
                  "the driver lives in (DCH 914.2.1). The active license is neither. Add the "
                  "license that is, or correct the driver's address if it is wrong.",
    "residenceunknown": "The active license is from a state bordering Georgia. Georgia Medicaid "
                        "accepts it only if the driver lives in that state (DCH 914.2.1), and the "
                        "driver's address has no state. Add it under Driver Information.",
    "notage18": "This driver is under 18. F.S. 316.302(4) does not permit them to operate a "
                "commercial motor vehicle, and nothing can be filed that changes it.",
    "notenglish": "Recorded as not able to read and speak English well enough for 49 CFR "
                  "391.11(b)(2). The driver is not qualified while that stands.",
    "paperstands": "The certificate on file is newer than the driving record, so the State has not "
                   "caught up yet. 49 CFR 391.51(b)(7)(i) lets the copy stand as proof for fifteen "
                   "days from the day it was issued.",
}

def _employer_standing(asked: list[dict]) -> tuple[str, str]:
    """Where the safety performance inquiries stand as one mark.

    An employer who never answered does not hold the requirement open for ever - 391.23(i) is
    satisfied by a documented good faith effort. What holds it open is an employer nobody has
    asked, or one asked and not yet chased to a conclusion."""
    if not asked:
        return "pending", "No previous employers are on file to ask."
    # A reply nobody has read does not answer the requirement. It arrived from outside this office
    # and may say the driver was dismissed or has accidents on their record.
    unread = [i["employer"] for i in asked if i["state"] == "toreview"]
    if unread:
        # Nothing to add to the mark: the eye already says a reply is waiting to be read, and the
        # dialog names whose.
        return "review", None
    unasked = [i["employer"] for i in asked if i["state"] == "notasked"]
    if unasked:
        return "pending", f'Not asked yet: {", ".join(unasked)}.'
    waiting = [i["employer"] for i in asked if i["state"] == "waiting"]
    if waiting:
        return "ordered", f'Asked and waiting on {", ".join(waiting)}.'
    efforts = sum(1 for i in asked if i["state"] == "effort")
    if efforts:
        return "satisfied", (f'{len(asked)} of {len(asked)} answered or closed as a good faith '
                             f'effort ({efforts} never replied).')
    return "satisfied", f'All {len(asked)} previous employers answered.'


def asked_of_driver(conn: Connection, accountid: str, driverid: str) -> dict[str, dict]:
    """What this driver has been asked for and has not sent yet, by credential code.

    A requirement nobody has chased and one the driver was asked for a fortnight ago are not the
    same state, and the mark should not read the same for both."""
    asked = {r["code"]: r for r in rows(conn, """
        SELECT credentialcode AS code, COALESCE(senton, createdon) AS askedon, sentto
        FROM uploadrequests
        WHERE accountid = :a AND driverid = :d AND uploadedon IS NULL AND cancelledon IS NULL
        ORDER BY createdon
    """, a=accountid, d=driverid)}
    # A document sent out to be signed is the same kind of fact: asked for, not back.
    asked.update({r["code"]: r for r in rows(conn, """
        SELECT doctype AS code, COALESCE(senton, createdon) AS askedon, sentto
        FROM signingrequests
        WHERE accountid = :a AND driverid = :d AND signedon IS NULL AND cancelledon IS NULL
        ORDER BY createdon
    """, a=accountid, d=driverid)})
    return asked


def adopted(conn: Connection, accountid: str) -> dict[str, dict]:
    """What this company has elected about each rule, by rule code.

    Absent means `regulation`, so a company that has never opened the page behaves exactly as it
    did before the page existed."""
    return {r["rulecode"]: r for r in rows(conn, """
        SELECT rulecode, applyto, reason FROM companyrulepolicy WHERE accountid = :a
    """, a=accountid)}


def already_read(conn: Connection, accountid: str, driverid: str) -> set[tuple[str, str]]:
    """Every evidence record somebody in this office has said they have read, as (table, id).

    One place, whatever the record is. A reading is the same act whether what was read is a
    laboratory result, a medical certificate, a license copy or a federal database answer, and
    giving each kind its own flag is how one of them ends up without one.

    A signed document is the exception that proves the point. Its reading is recorded against the
    SIGNING REQUEST - that is the row that knows the thing came from outside - and the evidence
    the engine reads is the signature it produced. Two rows for one act, so the act has to be
    carried from one to the other here. Without this an I-9 that the employer had certified under
    penalty of perjury, and a W-4 somebody had marked reviewed, both sat in "Waiting To Be
    Reviewed" for good: the signing request said read, the engine was looking somewhere else, and
    nothing anybody could click would ever clear them.
    """
    return {(r["sourcetable"], r["sourceid"]) for r in rows(conn, """
        SELECT sourcetable, sourceid FROM documentreads
        WHERE accountid = :a AND subject = 'driver' AND subjectid = :d
        UNION
        SELECT 'documentsignatures' AS sourcetable, ds.recordid AS sourceid
        FROM signingrequests sr
        JOIN documentsignatures ds
          ON ds.accountid = sr.accountid AND ds.ownerid = sr.driverid
         AND ds.ownertype = 'driver' AND ds.doctype = sr.doctype
        WHERE sr.accountid = :a AND sr.driverid = :d
          AND sr.reviewedon IS NOT NULL AND sr.cancelledon IS NULL
    """, a=accountid, d=driverid)}


def awaiting_review(conn: Connection, accountid: str, driverid: str) -> set[str]:
    """Documents this driver sent in themselves that nobody in the office has checked yet.

    Everything else on a file was put there by somebody who had it open and looked at it. A document
    that arrives down a link had none of that - it may be the wrong one, an expired one, or a
    photograph of something else - so a requirement does not stand on it until somebody says they
    have read it."""
    return {r["documentid"] for r in rows(conn, """
        SELECT documentid FROM uploadrequests
        WHERE accountid = :a AND driverid = :d AND documentid IS NOT NULL AND reviewedon IS NULL
    """, a=accountid, d=driverid) if r["documentid"]}


def read_documents(conn: Connection, accountid: str, driverid: str) -> set[str]:
    """Documents this driver sent in that somebody in the office HAS read.

    The other half of `awaiting_review`. Reading the paper is reading the record it became: a
    medical certificate opened, looked at and marked reviewed is read, and the credential row it
    created carries no separate reading because there was only ever one act. Without this the
    office reads the certificate, the upload request records it, and the requirement goes on saying
    it is waiting to be checked - which is what happened.

    A document that arrived by SIGNATURE rather than by upload is handled in `already_read`, by
    the record it produced: the evidence a signature rule stands on carries no document id."""
    return {r["documentid"] for r in rows(conn, """
        SELECT documentid FROM uploadrequests
        WHERE accountid = :a AND driverid = :d AND documentid IS NOT NULL
          AND reviewedon IS NOT NULL
    """, a=accountid, d=driverid) if r["documentid"]}


# What each thing asked of a driver ANSWERS. One submission can settle more than one requirement -
# the 40.25(j) questionnaire asks whether there was a violation and, if there was, whether the
# return-to-duty process was completed - and both answers arrived together, unread together.
ANSWERS = {
    "PREEMP_DA_QUESTIONNAIRE": ("priorviolation", "priorrtdcomplete"),
    # Not an answer but a reply to the same question: the paperwork behind the claim.
    "RTD_DOCUMENTATION": ("priorrtdcomplete",),
}


def answered_unread(conn: Connection, accountid: str, driverid: str) -> set[str]:
    """Everything that came back from OUTSIDE this office and nobody here has read yet, by the code
    it was asked for.

    This is the general form of the rule, and the rule is simple: anything sent in by somebody who
    is not in this office - the driver, a previous employer, an agency - is unread until a person
    here says they read it. It does not matter whether it arrived as a document, as an answer typed
    onto an application, or as a license card with two photographs of it.

    Keyed on what was ASKED FOR rather than on the document that came back, because the record the
    requirement reads is not always the document that arrived: a driver sends a new license, the
    rule reads whichever license is active, and matching documents would quietly let the new one
    through unread."""
    out = {r["credentialcode"] for r in rows(conn, """
        SELECT credentialcode FROM uploadrequests
        WHERE accountid = :a AND driverid = :d AND uploadedon IS NOT NULL
          AND reviewedon IS NULL AND cancelledon IS NULL AND credentialcode IS NOT NULL
    """, a=accountid, d=driverid)}
    # And the other way a driver answers a link: by signing. A different table, the same rule - and
    # the reason this gate has had to be widened twice is that it was built around one of them.
    # A signature rule's evidence source is `signature:<DOCTYPE>`, so the doctype is the key.
    out |= {r["doctype"] for r in rows(conn, """
        SELECT doctype FROM signingrequests
        WHERE accountid = :a AND driverid = :d AND signedon IS NOT NULL
          AND reviewedon IS NULL AND cancelledon IS NULL
    """, a=accountid, d=driverid)}
    # And a road test, administered by an examiner who is usually not in this office either.
    if row(conn, """
        SELECT 1 AS x FROM roadtests
        WHERE accountid = :a AND driverid = :d AND completedon IS NOT NULL AND reviewedon IS NULL
    """, a=accountid, d=driverid):
        out.add("ROAD_TEST")
    return out


def _asked_code(rule: dict) -> str:
    """What this rule is asked for BY - the code an upload request would carry for it.

    The evidence source says where the answer lives; this says what the office would ask the driver
    for to get one. They differ in exactly the places that have caused trouble: a license is asked
    for as DRIVER_LICENSE and read from `driverlicenses`, and the questionnaire is asked for by its
    own code and read from an answer on the application."""
    kind, _, which = (rule.get("evidencesource") or "").partition(":")
    if kind == "licensecopy":
        return "DRIVER_LICENSE"
    if kind.startswith("applicationanswer"):
        for code, facts_ in ANSWERS.items():
            if which in facts_:
                return code
    return which or rule.get("code") or ""


def _evidence(conn: Connection, accountid: str, driverid: str, source: str | None,
              facts: dict | None = None) -> dict | None:
    """The newest record that speaks to this rule, or None if there is not one."""
    if not source:
        return None
    kind, _, which = source.partition(":")

    if kind == "credential":
        return _credential_life(row(conn, """
            SELECT c.recordid, c.issuedon AS effectiveon, c.expireson, c.exempt, c.documentid,
                   t.maxagedays, t.defaultvaliddays,
                   'credentials' AS sourcetable,
                   -- Some training is not finished when the class is. Where the TYPE says the
                   -- skill has to be demonstrated, a record with no testing date is a record of
                   -- attendance, and attendance is not what F.A.C. 14-90.004(3)(d) asks for.
                   CASE WHEN t.requirestesting = 1 AND c.testedon IS NULL THEN 'untested'
                        -- A screen that came back positive, or was refused, is not one passed.
                        WHEN c.result IN ('positive', 'refusal') THEN 'positive'
                        WHEN c.result = 'negative' THEN 'negative'
                        -- A screening that must say where it came from, and does not, or came
                        -- from a vendor rather than the authority itself.
                        WHEN t.requiresprovenance = 1
                             AND COALESCE(c.provenance, 'vendor') = 'vendor' THEN 'noprovenance'
                        END AS determination,
                   c.testedon, c.testedby
            FROM credentials c JOIN credentialtypes t ON t.recordid = c.credentialtypeid
            WHERE c.accountid = :a AND c.subject = 'driver' AND c.subjectid = :d AND t.code = :code
              AND c.deleted IS NULL AND c.revokedon IS NULL
            ORDER BY c.issuedon DESC, c.added DESC LIMIT 1
        """, a=accountid, d=driverid, code=which))

    if kind == "mvr":
        return row(conn, """
            SELECT recordid, issuedon AS effectiveon, NULL AS expireson, 0 AS exempt, documentid,
                   'drivermvrs' AS sourcetable,
                   CASE WHEN finding = 'disqualified' THEN 'disqualified'
                        WHEN reviewstate = 'reviewed' THEN 'reviewed'
                        ELSE NULL END AS determination
            FROM drivermvrs WHERE accountid = :a AND driverid = :d AND receivedon IS NOT NULL
            -- A record that disqualifies outranks anything filed after it. It is a state the
            -- driver is in from the moment somebody read it, not an observation a later clean
            -- record quietly supersedes.
            ORDER BY (finding = 'disqualified') DESC, issuedon DESC, receivedon DESC LIMIT 1
        """, a=accountid, d=driverid)

    if kind == "license":
        # The license itself, not a copy of it. 391.11(b)(5) asks whether the driver holds one
        # and whether it is valid FOR THE VEHICLE THEY OPERATE - a question the record answers
        # whether or not anybody has photographed the card.
        #
        # This used to hand back "qualified" as a literal in the SELECT, whatever it found. So a
        # driver assigned Class B heavy CDL work passed with a Class E operator license, passed
        # with a license marked not active, and passed with no license on file at all - because
        # the comparison the regulation is ABOUT was never made. The only thing being checked was
        # the expiry date of whatever row came back first.
        held = row(conn, """
            SELECT recordid, issued AS effectiveon, expires AS expireson, 0 AS exempt,
                   copydocumentid AS documentid, 'driverlicenses' AS sourcetable,
                   classification, commercial, active, number, state
            FROM driverlicenses
            WHERE accountid = :a AND driverid = :d
            ORDER BY active DESC, expires DESC LIMIT 1
        """, a=accountid, d=driverid)
        if not held:
            # No row at all. Said as a determination rather than by returning None, because None
            # means "nothing filed yet" and reads as an errand; this is a driver who may not drive.
            return {"recordid": f"{driverid}:license", "effectiveon": None, "expireson": None,
                    "exempt": 0, "documentid": None, "sourcetable": "driverlicenses",
                    "determination": "nolicense"}
        verdict = _license_verdict(held, facts or {})
        if verdict == "qualified" and which == "georgia":
            verdict = _georgia_license(conn, accountid, driverid, held)
        if verdict == "wrongclass":
            return {**held, "determination": verdict,
                    "said": _wrong_class_says(conn, accountid, driverid, held, facts or {})}
        return {**held, "determination": verdict}

    if kind == "driverfact":
        # A requirement answered by something already known rather than by a document. Age is the
        # first of these and English proficiency is the obvious next: there is nothing to file, the
        # fact is either established or it is not, and three-valued throughout - unknown is not a
        # pass.
        said = (facts or {}).get(which)
        if said is None:
            return None
        # Named after the fact it failed rather than a bare "disqualified", so the sentence can
        # say what is actually wrong. A fact nobody can satisfy by filing anything deserves a
        # sentence that does not send somebody looking for a document.
        return {"recordid": f"{driverid}:{which}", "effectiveon": None, "expireson": None,
                "exempt": 0, "documentid": None, "sourcetable": "drivers",
                "determination": "qualified" if said else f"not{which.rpartition('.')[2]}"}

    if kind == "licensematch":
        # Not a document and nothing to file. The answer is a comparison between two things already
        # on the record: what this work needs, and what the license carries. An endorsement the
        # driver does not hold cannot be uploaded - it is obtained from the licensing State - so the
        # requirement is answered by the license changing, not by paper arriving.
        held = row(conn, """
            SELECT d.recordid, d.endorsementsneeded,
                   COALESCE(l.endorsements, d.endorsements) AS endorsements,
                   l.recordid AS licenseid, l.issued AS effectiveon, l.expires AS expireson
            FROM drivers d
            LEFT JOIN driverlicenses l ON l.driverid = d.recordid AND l.accountid = d.accountid
                 AND l.active = 1
            WHERE d.recordid = :d AND d.accountid = :a
            ORDER BY l.issued DESC LIMIT 1
        """, a=accountid, d=driverid)
        if not held or not (held.get("endorsementsneeded") or "").strip():
            return None
        needed = set(ENDORSEMENTS(held["endorsementsneeded"]))
        has = set(ENDORSEMENTS(held["endorsements"]))
        missing = sorted(needed - has)
        return {"recordid": held["recordid"], "effectiveon": held.get("effectiveon"),
                "expireson": held.get("expireson"), "exempt": 0, "documentid": None,
                "sourcetable": "drivers",
                "determination": "missing" if missing else "endorsed",
                "missing": missing, "needed": sorted(needed), "held": sorted(has)}

    if kind == "cdlismedical":
        # What the State holds, read off the driving record this office already pulls. The
        # comparison with the paper certificate is made here rather than on a screen, because a
        # discrepancy that only appears when somebody opens the right panel is a discrepancy
        # nobody finds.
        #
        # Done in Python rather than as one nested CASE: the order of the tests IS the reasoning,
        # and it does not survive being written as SQL.
        got = row(conn, """
            SELECT m.recordid, m.issuedon AS effectiveon, m.medcertexpires AS expireson, 0 AS exempt,
                   m.documentid, 'drivermvrs' AS sourcetable,
                   m.selfcert, m.medcertstatus, m.medcertexpires,
                   card.issuedon AS cardissued, card.expireson AS cardexpires
            FROM drivermvrs m
            -- THE card, not the latest date across all of them. A driver with five certificates
            -- on file has one that governs - the newest issued, which is the one the medical
            -- certificate requirement itself reads - and comparing against the furthest expiry in
            -- the pile invents a discrepancy out of a superseded card.
            LEFT JOIN (
                SELECT c.issuedon, c.expireson
                FROM credentials c JOIN credentialtypes t ON t.recordid = c.credentialtypeid
                WHERE c.accountid = :a AND c.subject = 'driver' AND c.subjectid = :d
                  AND t.code = 'DOT_MEDICAL_CARD' AND c.deleted IS NULL AND c.revokedon IS NULL
                ORDER BY c.issuedon DESC, c.added DESC LIMIT 1
            ) card ON 1 = 1
            WHERE m.accountid = :a AND m.driverid = :d AND m.receivedon IS NOT NULL
              AND m.medcertstatus IS NOT NULL
            -- A record saying "not certified" outranks anything filed after it, for the same
            -- reason a disqualifying driving record does: it is a state the driver is in.
            ORDER BY (m.medcertstatus = 'notcertified') DESC, m.issuedon DESC, m.receivedon DESC
            LIMIT 1
        """, a=accountid, d=driverid)
        if not got:
            return None
        return {**got, **_cdlis_reading(got, date.today())}

    if kind == "annualreview":
        got = row(conn, """
            SELECT recordid, reviewedon AS effectiveon, NULL AS expireson, 0 AS exempt, documentid,
                   'annualreviews' AS sourcetable, finding AS determination
            FROM annualreviews WHERE accountid = :a AND driverid = :d AND reviewedon IS NOT NULL
            ORDER BY reviewedon DESC, COALESCE(completedon, createdon) DESC, createdon DESC LIMIT 1
        """, a=accountid, d=driverid)
        # A driving record received since this review was made has been reviewed by nobody, so
        # the review stops answering until another is completed against it.
        if got:
            from app import annualreview
            newer = annualreview.newer_record(conn, accountid, driverid, got["recordid"],
                                              got["effectiveon"])
            if newer:
                got = {**got, "determination": "newermvr", "newer": newer["receivedon"]}
        return got

    if kind == "report":
        return row(conn, """
            SELECT recordid, issuedon AS effectiveon, NULL AS expireson, 0 AS exempt, documentid,
                   'driverreports' AS sourcetable, COALESCE(outcome, reviewstate) AS determination,
                   reviewstate
            FROM driverreports WHERE accountid = :a AND driverid = :d AND code = :code
              AND receivedon IS NOT NULL
            ORDER BY issuedon DESC, receivedon DESC LIMIT 1
        """, a=accountid, d=driverid, code=which)

    if kind == "roadtest":
        # 49 CFR 391.31: the certificate is the output of a test somebody administered, so the
        # record IS the evidence. Unread tests are deliberately included - the gate below turns
        # them into "waiting to be checked" rather than letting them answer anything.
        return row(conn, """
            SELECT recordid, testedon AS effectiveon, NULL AS expireson, 0 AS exempt, documentid,
                   'roadtests' AS sourcetable,
                   CASE WHEN result = 'pass' THEN 'qualified'
                        WHEN result = 'fail' THEN 'disqualified' ELSE NULL END AS determination
            FROM roadtests WHERE accountid = :a AND driverid = :d AND completedon IS NOT NULL
            ORDER BY testedon DESC, completedon DESC LIMIT 1
        """, a=accountid, d=driverid)

    if kind == "drugtest" and which == "postaccident":
        # 382.303 asks for an alcohol test AND a controlled substances test after a qualifying
        # accident, and the accident register links each. The rule only reaches a driver while one
        # is owed, so any result on file is not the answer - the missing one is named instead.
        from app import accidents
        for crash in accidents.for_driver(conn, accountid, driverid):
            if crash.get("nottested") or not crash.get("required"):
                continue
            missing = [w for w, k in (("alcohol", "alcoholtestid"), ("controlled substances", "drugtestid"))
                       if not crash.get(k)]
            if missing:
                return {"recordid": crash["recordid"], "effectiveon": None, "expireson": None,
                        "exempt": 0, "documentid": None, "sourcetable": "driveraccidents",
                        "determination": "testsowed",
                        "said": (f"The accident on {crash['occurredon']:%m/%d/%Y} needs a post-accident "
                                 f"{' and '.join(missing)} test, and none is linked to it on the "
                                 f"accident register. Link the test, or record why it was not given.")}
        return None

    if kind == "drugtest":
        # A negative return-to-duty test answers the pre-employment requirement. 49 CFR 40.305 is
        # what permits the driver to work again, and 382.301(a) asks for a negative controlled
        # substances result before safety-sensitive work - not for one with a particular reason
        # printed on it. A driver who failed pre-employment and completed the return-to-duty
        # process is not sent back for another pre-employment collection, and the requirement must
        # not go on reading the old positive as if nothing had happened since.
        #
        # Only a return-to-duty test that actually LIFTED a bar counts: one taken while the SAP has
        # not signed the driver off has not finished anything.
        return row(conn, """
            SELECT t.recordid, t.collectedon AS effectiveon, NULL AS expireson, 0 AS exempt,
                   t.documentid, 'drugtests' AS sourcetable, t.result AS determination
            FROM drugtests t
            WHERE t.accountid = :a AND t.driverid = :d AND t.withdrawn IS NULL
              AND (t.reason = :reason
                   OR (:reason = 'preemployment' AND t.recordid IN (
                        SELECT p.rtdtestid FROM driverprohibitions p
                        WHERE p.accountid = :a AND p.driverid = :d AND p.withdrawn IS NULL
                          AND p.rtdtestid IS NOT NULL AND p.clearedon IS NOT NULL)))
            -- A test that raised a bar still in force outranks anything collected after it, for
            -- the same reason a disqualifying driving record does: it is a state the driver is in
            -- until the return-to-duty process ends it, not an observation a later clean result
            -- quietly supersedes. Taking another pre-employment test does not undo a violation -
            -- the violation is in the Clearinghouse either way - and a requirement that went green
            -- on the second collection would say the driver was cleared to do the very thing they
            -- are federally barred from. Once the bar IS cleared this falls away on its own and the
            -- newest result wins again.
            ORDER BY (t.recordid IN (
                        SELECT p.testid FROM driverprohibitions p
                        WHERE p.accountid = :a AND p.driverid = :d AND p.withdrawn IS NULL
                          AND p.testid IS NOT NULL AND p.clearedon IS NULL)) DESC,
                     t.collectedon DESC, t.createdon DESC
            LIMIT 1
        """, a=accountid, d=driverid, reason=which)

    # An answer the applicant gave on their own application, under their own signature. There is no
    # document to point at: the application IS the record, and the fact is read from it.
    if kind in ("applicationanswer", "applicationanswered"):
        return None

    if kind == "transitmedical":
        return row(conn, """
            SELECT recordid, examinedon AS effectiveon, qualifiedthrough AS expireson, 0 AS exempt,
                   documentid, 'transitmedicals' AS sourcetable,
                   -- A temporary disqualification stops the driver while it stands, so it reads
                   -- the same as not meeting the standards.
                   CASE WHEN result IN ('doesnotmeet', 'temporary') THEN 'disqualified'
                        ELSE 'qualified' END AS determination
            FROM transitmedicals
            WHERE accountid = :a AND driverid = :d AND deleted IS NULL
            ORDER BY (result IN ('doesnotmeet', 'temporary')) DESC,
                     examinedon DESC, createdon DESC LIMIT 1
        """, a=accountid, d=driverid)

    if kind == "signature":
        return row(conn, """
            SELECT recordid, DATE(signedon) AS effectiveon, NULL AS expireson, 0 AS exempt,
                   NULL AS documentid, 'documentsignatures' AS sourcetable, NULL AS determination
            FROM documentsignatures WHERE accountid = :a AND ownertype = 'driver' AND ownerid = :d
              AND doctype = :code
            ORDER BY signedon DESC LIMIT 1
        """, a=accountid, d=driverid, code=which)

    if kind == "exclusioncheck":
        return row(conn, """
            SELECT recordid, DATE(checkedon) AS effectiveon, NULL AS expireson, 0 AS exempt,
                   evidencedocid AS documentid, 'exclusionchecks' AS sourcetable,
                   CASE WHEN result = 'clear' THEN 'clear'
                        WHEN result = 'confirmed' THEN 'flagged'
                        ELSE 'review' END AS determination
            FROM exclusionchecks
            WHERE accountid = :a AND driverid = :d
              -- Every list, unless the rule names one. The requirement is "OIG LEIE and SAM.gov",
              -- so an exclusion recorded against SAM has to count: reading only OIG left a driver
              -- confirmed excluded on one list showing a green tick from the other.
              AND (:code = '' OR source = :code)
            -- Worst answer wins, not newest. A confirmed exclusion is a state somebody is in until
            -- it is lifted, and the monthly job writes a clear row every month - none of which can
            -- undo a person having checked the SSN and said yes. An unsettled possible match
            -- outranks a clear for the same reason: it is work nobody has finished.
            -- A lifted exclusion stops outranking. The row stays exactly as it was - what the
            -- file held the day a trip ran is the question an auditor asks - it just no longer
            -- describes where this driver stands today.
            -- The latest screening, always. The office's own rule: the requirement shows what the
            -- most recent check returned, and every earlier one is in the History.
            ORDER BY checkedon DESC LIMIT 1
        """, a=accountid, d=driverid, code=which)

    if kind == "dutyhours":
        # F.A.C. 14-90.006(3) and (5). Answered by the work on file, not by a document - see
        # app/hos.py, which owns the limits and the rolling seven-day window.
        from app import hos
        return hos.standing(conn, accountid, driverid)

    if kind == "prohibition":
        # The bar itself. 49 CFR 382.501: a driver who has tested positive, refused, or
        # otherwise violated Part 382 must be removed from safety-sensitive functions and stays
        # removed until the whole return-to-duty process in Part 40 Subpart O is complete.
        return row(conn, """
            SELECT recordid, startedon AS effectiveon, NULL AS expireson, 0 AS exempt,
                   documentid, 'driverprohibitions' AS sourcetable,
                   'prohibited' AS determination, reason, sapinfogivenon, sapcompliedon,
                   rtdtestid, decision
            FROM driverprohibitions
            WHERE accountid = :a AND driverid = :d AND clearedon IS NULL AND withdrawn IS NULL
            ORDER BY startedon DESC LIMIT 1
        """, a=accountid, d=driverid)

    if kind == "poolmember":
        # Membership is a span, so "was in the pool once" is not the answer - a driver taken out
        # in March is not in the pool in November, and the row that proves they were in March is
        # still on the record. Only an OPEN spell satisfies this.
        return row(conn, """
            SELECT recordid, joinedon AS effectiveon, NULL AS expireson, 0 AS exempt,
                   NULL AS documentid, 'randompoolmembership' AS sourcetable,
                   NULL AS determination
            FROM randompoolmembership
            WHERE accountid = :a AND driverid = :d AND leftpoolon IS NULL
            ORDER BY joinedon DESC LIMIT 1
        """, a=accountid, d=driverid)

    if kind == "atfaultcount":
        # DCH 914.2.5: two at-fault moving violations and/or accidents on NEMT work, and the driver
        # comes off. Counted from the accident register (where the driver was at fault) and the
        # moving violations recorded against them (where convicted and at fault). Nothing to file:
        # the answer is the count.
        hits = rows(conn, """
            SELECT DATE(occurredon) AS whenon, 'Accident' AS what FROM driveraccidents
            WHERE accountid = :a AND driverid = :d AND withdrawn IS NULL AND atfault = 1
            UNION ALL
            SELECT occurredon, violation FROM drivermovingviolations
            WHERE accountid = :a AND driverid = :d AND withdrawn IS NULL AND atfault = 1
              AND onnemt = 1 AND convictedon IS NOT NULL
            ORDER BY whenon DESC
        """, a=accountid, d=driverid)
        return {"recordid": f"{driverid}:atfault", "effectiveon": None, "expireson": None,
                "exempt": 0, "documentid": None, "sourcetable": "drivers",
                "determination": "removal" if len(hits) >= 2 else "withinlimit",
                "count": len(hits), "hits": hits}

    if kind == "drivingexperience":
        # Years of driving, read off the licenses on file. An issue date is usually the latest
        # renewal, so it proves the driver was licensed by then and no earlier: old enough settles
        # it, but a recent one may be a renewal and proves nothing either way. An original issue
        # date - printed on some cards, or given on the application - is the real start.
        # Nothing recorded is nothing on file - not a driver too new to drive.
        held = rows(conn, """
            SELECT issued, originalissued FROM driverlicenses WHERE accountid = :a AND driverid = :d
        """, a=accountid, d=driverid)
        declared = (row(conn, "SELECT licensesince FROM drivers WHERE recordid = :d AND accountid = :a",
                        d=driverid, a=accountid) or {}).get("licensesince")
        original = [x for x in [l["originalissued"] for l in held] + [declared] if x]
        every = original + [l["issued"] for l in held if l["issued"]]
        if not every:
            return None
        since = min(every)
        years = (date.today() - since).days / 365.25
        return {"recordid": f"{driverid}:experience", "effectiveon": since, "expireson": None,
                "exempt": 0, "documentid": None, "sourcetable": "driverlicenses",
                "determination": ("experienced" if years >= 3 else
                                  "inexperienced" if original else "unproven"),
                "licensesince": since}

    if kind == "securementclear":
        # DCH 907.16: one confirmed failure to secure a wheelchair takes the driver off until they
        # are retrained. Answered by securement training dated after the latest confirmed failure.
        failed = row(conn, """
            SELECT MAX(occurredon) AS lastfailed FROM driversecurementincidents
            WHERE accountid = :a AND driverid = :d AND confirmed = 1 AND withdrawn IS NULL
        """, a=accountid, d=driverid) or {}
        last = failed.get("lastfailed")
        trained = row(conn, """
            SELECT MAX(c.issuedon) AS trainedon FROM credentials c
            JOIN credentialtypes t ON t.recordid = c.credentialtypeid
            WHERE c.accountid = :a AND c.subject = 'driver' AND c.subjectid = :d
              AND t.code = 'WHEELCHAIR_SECUREMENT' AND c.deleted IS NULL AND c.revokedon IS NULL
              AND (:last IS NULL OR c.issuedon > :last)
        """, a=accountid, d=driverid, last=last) or {}
        return {"recordid": f"{driverid}:securement", "effectiveon": None, "expireson": None,
                "exempt": 0, "documentid": None, "sourcetable": "drivers",
                "determination": "noincident" if not last
                else "retrained" if trained.get("trainedon") else "awaitingretraining",
                "lastfailed": last, "trainedon": trained.get("trainedon")}

    if kind == "licensecopy":
        return row(conn, """
            SELECT recordid, issued AS effectiveon, expires AS expireson, 0 AS exempt,
                   copydocumentid AS documentid, 'driverlicenses' AS sourcetable,
                   NULL AS determination
            FROM driverlicenses WHERE accountid = :a AND driverid = :d AND copydocumentid IS NOT NULL
            ORDER BY active DESC, issued DESC LIMIT 1
        """, a=accountid, d=driverid)

    return None


# ------------------------------------------------------------------------------------------------
# Everything held against one rule, newest first.
#
# The same seven shapes `_evidence` knows, read as a list rather than as the newest one. A record
# that has been replaced is still a record: it is what the file held on the day a trip ran, and an
# auditor asking about last March is asking about it rather than about what is current.
# ------------------------------------------------------------------------------------------------
# Which table each evidence source lives in. `documentreads` keys a reading by (table, id), so a
# screen that wants to offer the reading needs to know which table it is looking at.
EVIDENCE_TABLES = {
    "credential": "credentials", "mvr": "drivermvrs", "annualreview": "annualreviews",
    "report": "driverreports", "transitmedical": "transitmedicals", "roadtest": "roadtests",
    "drugtest": "drugtests", "signature": "documentsignatures", "exclusioncheck": "exclusionchecks",
    "licensecopy": "driverlicenses", "license": "driverlicenses",
    "employerhistory": "employerinquiries",
    # Two that live on the driver row itself rather than in a table of their own. Missing here,
    # their history rows came back with no sourcetable, and the reading could not be recorded
    # against anything - the button posted a null and the server rejected it.
    "poolmember": "randompoolmembership", "cdlismedical": "drivermvrs",
}


def needs_reading(rule: dict, evidence: dict | None, read: set,
                  readdocs: set) -> bool:
    """Whether this record came from outside and nobody in this office has read it yet.

    The one test, written once. `for_driver` asks it to decide the status and the requirement
    screen asks it to decide whether to offer the reading, so the eye on the list and the button
    behind it can never disagree - which is exactly how a license copy came to sit in review with
    nowhere to review it.

    A record somebody has already judged counts as read, whatever the judgement was: a query marked
    prohibited has plainly been looked at."""
    if not evidence or (rule.get("origin") or "thirdparty") == "office":
        return False
    judged = evidence.get("determination")
    if judged and str(judged).lower() not in REVIEWING:
        return False
    table = evidence.get("sourcetable")
    return ((table, evidence.get("recordid")) not in read
            and evidence.get("documentid") not in readdocs)


def history(conn: Connection, accountid: str, driverid: str, source: str | None) -> list[dict]:
    if not source:
        return []
    kind, _, which = source.partition(":")
    # A comparison has no history. There is one answer and it is the state of the license now, so
    # the detail screen is handed exactly what the engine read rather than a table of past answers
    # that were never recorded.
    if kind in ("licensematch", "cdlismedical"):
        got = _evidence(conn, accountid, driverid, source)
        return [got] if got else []
    args = {"a": accountid, "d": driverid, "code": which, "reason": which}

    table = EVIDENCE_TABLES.get(kind)
    sql = {
        "credential": """
            SELECT c.recordid, c.issuedon AS effectiveon, c.expireson, c.exempt, c.documentid,
                   t.maxagedays, t.defaultvaliddays,
                   NULL AS determination, c.notes AS note, c.added AS recordedon,
                   -- When the skill was demonstrated, and to whom. Blank on everything that is
                   -- not training that has to be shown.
                   c.testedon, c.testedby, c.screentype, c.result, c.provenance,
                   -- Who gave it. On a training record this is the whole point: no federal rule
                   -- names a trainer, so "trained by whom" is a fact only the record can answer.
                   c.issuer
            FROM credentials c JOIN credentialtypes t ON t.recordid = c.credentialtypeid
            WHERE c.accountid = :a AND c.subject = 'driver' AND c.subjectid = :d AND t.code = :code
              AND c.deleted IS NULL AND c.revokedon IS NULL
            ORDER BY c.issuedon DESC, c.added DESC""",
        "mvr": """
            SELECT m.recordid, m.issuedon AS effectiveon, NULL AS expireson, 0 AS exempt,
                   m.documentid,
                   CASE WHEN m.reviewstate = 'reviewed' THEN 'reviewed' ELSE NULL END AS determination,
                   m.note, COALESCE(m.receivedon, m.orderedon) AS recordedon,
                   -- Which license it was pulled on, because that is what a driving record is about,
                   -- and the two dates, because sent-for and received are different states.
                   -- Withdrawn as well as sent-for and received. A request somebody cancelled is
                   -- part of the record and stays in the history, but it is NOT outstanding: a
                   -- screen that sees only a date and no receipt would offer to fill it, and the
                   -- answer it tried to file would have nothing to attach to.
                   CONCAT(l.state, ' ', l.number) AS license, m.licenseid AS licenseid,
                   m.orderedon, m.receivedon, m.cancelledon
            FROM drivermvrs m LEFT JOIN driverlicenses l ON l.recordid = m.licenseid
            WHERE m.accountid = :a AND m.driverid = :d
            ORDER BY COALESCE(m.issuedon, m.orderedon) DESC, m.createdon DESC""",
        "annualreview": """
            SELECT recordid, reviewedon AS effectiveon, NULL AS expireson, 0 AS exempt, documentid,
                   finding AS determination, note, createdon AS recordedon
            FROM annualreviews WHERE accountid = :a AND driverid = :d
            ORDER BY reviewedon DESC, COALESCE(completedon, createdon) DESC, createdon DESC""",
        "report": """
            SELECT recordid, issuedon AS effectiveon, NULL AS expireson, 0 AS exempt, documentid,
                   COALESCE(outcome, reviewstate) AS determination, note,
                   COALESCE(receivedon, orderedon) AS recordedon
            FROM driverreports WHERE accountid = :a AND driverid = :d AND code = :code
            ORDER BY COALESCE(issuedon, orderedon) DESC, createdon DESC""",
        "transitmedical": """
            SELECT recordid, examinedon AS effectiveon, qualifiedthrough AS expireson, 0 AS exempt,
                   documentid, examtype, examinername, examinerlicense, examinerstate, examinertype,
                   result, correctivelenses, hearingaid, otherrestriction,
                   tempreason, followupon, createdon AS recordedon,
                   CASE WHEN result IN ('doesnotmeet', 'temporary') THEN 'disqualified'
                        ELSE 'qualified' END AS determination,
                   NULL AS note
            FROM transitmedicals WHERE accountid = :a AND driverid = :d AND deleted IS NULL
            ORDER BY examinedon DESC, createdon DESC""",
        "roadtest": """
            SELECT recordid, testedon AS effectiveon, NULL AS expireson, 0 AS exempt, documentid,
                   CASE WHEN result = 'pass' THEN 'qualified'
                        WHEN result = 'fail' THEN 'disqualified' ELSE NULL END AS determination,
                   comments AS note, completedon AS recordedon
            FROM roadtests WHERE accountid = :a AND driverid = :d AND completedon IS NOT NULL
            ORDER BY testedon DESC, completedon DESC""",
        "drugtest": """
            SELECT recordid, collectedon AS effectiveon, NULL AS expireson, 0 AS exempt, documentid,
                   result AS determination, note, createdon AS recordedon
            FROM drugtests WHERE accountid = :a AND driverid = :d AND reason = :reason
              AND withdrawn IS NULL
            ORDER BY collectedon DESC, createdon DESC""",
        "signature": """
            SELECT recordid, DATE(signedon) AS effectiveon, NULL AS expireson, 0 AS exempt,
                   NULL AS documentid, NULL AS determination, NULL AS note, signedon AS recordedon
            FROM documentsignatures WHERE accountid = :a AND ownertype = 'driver' AND ownerid = :d
              AND doctype = :code
            ORDER BY signedon DESC""",
        # A comparison has no history: there is one answer, which is the state of the license now.
        # Handled in history() itself rather than as SQL - see below.
        # Every driving record that carried medical certification information, newest first. The
        # same records the driving-record requirement lists, read for what else is on them.
        "cdlismedical": """
            SELECT recordid, issuedon AS effectiveon, medcertexpires AS expireson, 0 AS exempt,
                   documentid,
                   CASE
                     WHEN selfcert IN ('EI', 'NA', 'EA') THEN 'excepted'
                     WHEN medcertstatus = 'notcertified' THEN 'notcertified'
                     WHEN medcertstatus = 'notshown' AND selfcert = 'NI' THEN 'notcertified'
                     WHEN medcertstatus = 'notshown' THEN 'notshown'
                     WHEN medcertstatus = 'certified' THEN 'certified'
                     ELSE NULL END AS determination,
                   note, receivedon AS recordedon,
                   selfcert, medcertstatus, medcertexpires, medvariancetype, medvariance
            FROM drivermvrs
            WHERE accountid = :a AND driverid = :d AND receivedon IS NOT NULL
              AND medcertstatus IS NOT NULL
            ORDER BY issuedon DESC, receivedon DESC""",
        "exclusioncheck": """
            SELECT recordid, DATE(checkedon) AS effectiveon, NULL AS expireson, 0 AS exempt,
                   evidencedocid AS documentid,
                   CASE WHEN result = 'clear' THEN 'clear'
                        WHEN result = 'confirmed' THEN 'flagged'
                        ELSE 'review' END AS determination,
                   namessearched AS note, checkedon AS recordedon,
                   candidates AS candidatesjson, source, liftedon, liftreason,
                   -- Which published list the check was run against, and who settled it.
                   (SELECT x.datasetstamp FROM exclusionruns x WHERE x.recordid = e.runid)
                     AS datasetstamp,
                   e.performedby, e.verifiedon, e.verifymethod,
                   (SELECT u.name FROM users u WHERE u.recordid = e.verifiedby) AS verifiedbyname
            -- Every list, not only the one the rule is named after. A check recorded against SAM
            -- or Florida is part of this driver's screening history and would otherwise vanish the
            -- moment it was filed.
            FROM exclusionchecks e WHERE e.accountid = :a AND e.driverid = :d
            ORDER BY e.checkedon DESC""",
        "poolmember": """
            SELECT recordid, joinedon AS effectiveon, leftpoolon AS expireson, 0 AS exempt,
                   NULL AS documentid, NULL AS determination,
                   COALESCE(reason, CASE WHEN leftpoolon IS NULL THEN 'In the random testing pool'
                                         ELSE 'Taken out of the random testing pool' END) AS note,
                   added AS recordedon
            FROM randompoolmembership
            WHERE accountid = :a AND driverid = :d
            ORDER BY joinedon DESC, added DESC""",
        "licensecopy": """
            SELECT recordid, issued AS effectiveon, expires AS expireson, 0 AS exempt,
                   copydocumentid AS documentid, NULL AS determination,
                   CONCAT(state, ' ', number) AS note, added AS recordedon
            FROM driverlicenses WHERE accountid = :a AND driverid = :d
            ORDER BY active DESC, issued DESC""",
    }.get(kind)
    if not sql:
        return []
    # Which table each row came out of, so the screen can offer the reading against it. Added here
    # rather than written into ten SELECTs, where one of them would eventually be missed.
    out = [{**r, "sourcetable": r.get("sourcetable") or table} for r in rows(conn, sql, **args)]
    return [_credential_life(r) for r in out] if kind == "credential" else out


def _credential_life(got):
    """The expiry a credential actually has, which is not always the one printed on it.

    A license or an insurance certificate carries its own date. A training certificate usually
    does not, and what limits it is the TYPE: HIPAA privacy training is good for a year, CPR for
    two, defensive driving for three. Those limits have always been on credentialtypes as
    maxagedays and defaultvaliddays, and app/validity.py has always known how to read them - the
    rules engine simply never asked, and took c.expireson as the whole answer.

    So a HIPAA training certificate with no printed date read as "on file" with no expiry, sat on
    the validity-tracked list for ever saying nothing, and the annual refresher it is there to
    bring round never came due. That is not a cosmetic fault on a panel: it is a requirement that
    silently stopped recurring.

    The arithmetic is validity.credential_window and nothing else, because there is one
    definition of it. `end` is exclusive, so the last day the credential covers is the day
    before it.
    """
    if not got or not got.get("effectiveon"):
        return got
    out = dict(got)
    maxage = out.pop("maxagedays", None)
    default = out.pop("defaultvaliddays", None)
    # An exemption means there is no card to age, so the type's own limit must not retire it -
    # the record would lapse with no date on screen to explain why. Same call the evaluator makes.
    window = validity.credential_window(out["effectiveon"], out.get("expireson"), None,
                                        None if out.get("exempt") else maxage, 0, default)
    out["expireson"] = None if window.end is None else (window.end - timedelta(days=1)).date()
    return out


# What each class of license permits, as 49 CFR 383.91 divides them. A and B are the heavy
# commercial classes; C is commercial but under 26,001 lb (16 or more passengers, or placarded
# hazardous materials); D and E are ordinary operator licenses and M is a motorcycle.
#
# Kept here rather than read off a "is it commercial" flag because the question is not whether
# the license is commercial - it is whether it covers the work. A Class C CDL is a commercial
# license and does not permit a 26,001 lb vehicle.
HEAVY_CLASSES = ("A", "B")
CDL_CLASSES = ("A", "B", "C")


def _license_verdict(held: dict, facts: dict) -> str:
    """Whether this license qualifies this driver for the work they are assigned.

    Expiry is NOT decided here - `expireson` is on the record and the engine's own date
    arithmetic reads it, the same way it does for every other credential. What is decided here
    is the pair of questions that arithmetic cannot answer: is the license still held, and is it
    of a class that covers the vehicle.

    Read off the same two facts the rest of the engine uses, so there is one answer to "does
    this driver need a CDL" rather than a second one spelled out here that can drift from it.
    Three-valued: where nobody has said what the driver operates, the class is not asserted to
    be wrong - an unanswered question is not a failure."""
    if not held.get("active"):
        return "licenseinactive"
    # A class letter does not say commercial - Georgia's ordinary license is a Class C. Where the
    # record says the license is NOT a CDL, it does not cover CDL work whatever its letter.
    if (facts.get("driver.heavy") is True or facts.get("driver.cdl") is True) \
            and held.get("commercial") is not None and not held["commercial"]:
        return "wrongclass"
    carried = (held.get("classification") or "").upper()
    if facts.get("driver.heavy") is True:
        # 26,001 lb or more. A Class C CDL is a commercial license and does not cover it.
        return "qualified" if carried in HEAVY_CLASSES else "wrongclass"
    if facts.get("driver.cdl") is True:
        return "qualified" if carried in CDL_CLASSES else "wrongclass"
    return "qualified"


# What each class covers, in the words somebody at the desk would use.
CLASS_COVERS = {"A": "combination vehicles of 26,001 lb or more",
                "B": "single vehicles of 26,001 lb or more",
                "C": "vehicles under 26,001 lb carrying 16 or more people or placarded hazmat",
                "D": "ordinary vehicles - not a commercial license",
                "E": "ordinary vehicles - not a commercial license"}


# DCH 914.2.1: a current valid Georgia license, or one from the bordering state the driver lives in.
GEORGIA_BORDER = ("AL", "FL", "NC", "SC", "TN")


def _georgia_license(conn: Connection, accountid: str, driverid: str, held: dict) -> str:
    """Whether the license on file is one Georgia Medicaid accepts: Georgia's own, or that of a
    bordering state the driver lives in. Where they live is not on file, a bordering state's
    license cannot be judged and is left for somebody to look at."""
    state = (held.get("state") or "").upper()
    if state == "GA":
        return "qualified"
    if state not in GEORGIA_BORDER:
        return "notgeorgia"
    lives = ((row(conn, "SELECT state FROM drivers WHERE recordid = :d AND accountid = :a",
                  d=driverid, a=accountid) or {}).get("state") or "").upper()
    if not lives:
        return "residenceunknown"
    return "qualified" if lives == state else "notgeorgia"


def _wrong_class_says(conn: Connection, accountid: str, driverid: str, held: dict,
                      facts: dict) -> str:
    """Why this license does not fit the work, naming the license, what the work needs and why, and
    the way out - including a license already on file that would fit, if there is one."""
    heavy = facts.get("driver.heavy") is True
    if held.get("commercial") is not None and not held["commercial"]:
        which = " ".join(x for x in (held.get("state"), f"Class {held.get('classification')}"
                                     if held.get("classification") else None) if x)
        return (f"The active license ({which or 'on file'}) is recorded as not a commercial "
                f"license, and Company Information says this driver will operate a vehicle that "
                f"{'is rated 26,001 lb or more' if heavy else 'requires a CDL'}. Add the CDL under "
                f"Licenses, or correct the license if it is in fact commercial.")
    fits = HEAVY_CLASSES if heavy else CDL_CLASSES
    carried = (held.get("classification") or "").upper()
    which = " ".join(x for x in (held.get("state"), f"Class {carried}" if carried else None) if x)
    covers = CLASS_COVERS.get(carried)
    ticked = "26,001 lb or more" if heavy else "requires a CDL"
    number = f" ({held['number']})" if held.get("number") else ""
    out = (f"The active license is {which or 'on file'}{number}"
           f"{f', which covers {covers}' if covers else ''}. Company Information says this driver "
           f"will operate a vehicle that {'is rated ' if heavy else ''}{ticked}, which needs a "
           f"Class {' or '.join(fits) if len(fits) == 2 else 'A, B or C'} license. ")
    other = row(conn, f"""
        SELECT number, state, classification FROM driverlicenses
        WHERE accountid = :a AND driverid = :d AND recordid <> :r
          AND UPPER(classification) IN ({", ".join(repr(c) for c in fits)})
          AND (expires IS NULL OR expires >= CURDATE())
        ORDER BY expires DESC LIMIT 1
    """, a=accountid, d=driverid, r=held["recordid"])
    if other:
        out += (f"A {other['state']} Class {other['classification'].upper()} ({other['number']}) is on "
                f"file but not marked active - open it under Licenses and press Make Active")
    else:
        out += "Add the license that covers this work under Licenses"
    return out + f", or untick \"{ticked}\" if this driver will not operate such a vehicle."


def _filed(conn: Connection, accountid: str, driverid: str, ruleid: str,
           subject: str = "driver") -> dict | None:
    """A document filed directly against this requirement.

    The fallback for everything the application cannot produce itself. A DOT application signed on
    paper answers 49 CFR 391.21 exactly as well as one signed through the wizard, and a file with
    the paper copy in it is not less compliant for having arrived by scanner."""
    return row(conn, """
        SELECT e.recordid, e.effectiveon, e.expireson, 0 AS exempt, e.sourceid AS documentid,
               'complianceevidence' AS sourcetable, e.determination
        FROM complianceevidence e
        WHERE e.accountid = :a AND e.subject = :s AND e.subjectid = :d AND e.ruleid = :r
        ORDER BY e.effectiveon DESC, e.added DESC LIMIT 1
    """, a=accountid, d=driverid, r=ruleid, s=subject)


def filed_history(conn: Connection, accountid: str, driverid: str, ruleid: str) -> list[dict]:
    return rows(conn, """
        SELECT e.recordid, e.effectiveon, e.expireson, 0 AS exempt, e.sourceid AS documentid,
               e.determination, e.note, e.added AS recordedon, 'filed' AS source
        FROM complianceevidence e
        WHERE e.accountid = :a AND e.subject = 'driver' AND e.subjectid = :d AND e.ruleid = :r
        ORDER BY e.effectiveon DESC, e.added DESC
    """, a=accountid, d=driverid, r=ruleid)


def _ordered(conn: Connection, accountid: str, driverid: str, source: str | None) -> dict | None:
    """Something asked for and not back yet, whoever it was asked of.

    A requirement nobody has chased and one that is out for signature are not the same state, and
    the mark must not read the same for both. Anything that can be sent away for belongs here: a
    report ordered from a service, a driving record from a state, a document sent to the driver to
    sign. The one thing it never means is that the requirement is met."""
    if not source:
        return None
    kind, _, which = source.partition(":")
    if kind == "signature":
        return row(conn, """
            SELECT COALESCE(senton, createdon) AS orderedon FROM signingrequests
            WHERE accountid = :a AND driverid = :d AND doctype = :code
              AND signedon IS NULL AND cancelledon IS NULL
            ORDER BY createdon DESC LIMIT 1
        """, a=accountid, d=driverid, code=which)
    if kind == "report":
        return row(conn, """
            SELECT orderedon FROM driverreports
            WHERE accountid = :a AND driverid = :d AND code = :code
              AND orderedon IS NOT NULL AND receivedon IS NULL
            ORDER BY orderedon DESC LIMIT 1
        """, a=accountid, d=driverid, code=which)
    if kind == "mvr":
        return row(conn, """
            SELECT orderedon FROM drivermvrs
            WHERE accountid = :a AND driverid = :d AND orderedon IS NOT NULL AND receivedon IS NULL
            ORDER BY orderedon DESC LIMIT 1
        """, a=accountid, d=driverid)
    return None


# ------------------------------------------------------------------------------------------------
# Where a rule stands.
#
# The statuses are kept apart because they are different jobs for the office. Expired is not
# failed; failed is not pending; and a rule that does not reach this driver is not outstanding
# work, it is nothing at all.
# ------------------------------------------------------------------------------------------------
WARN_DAYS = 30


# What each letter is, so a screen can say "P (passenger)" rather than make somebody know.
ENDORSEMENT_NAMES = {
    "H": "hazardous materials", "N": "tank vehicle", "P": "passenger",
    "S": "school bus", "T": "double/triple trailers", "X": "tank and hazardous materials",
}


def ENDORSEMENTS(raw: str | None) -> list[str]:
    """The endorsement letters in a field somebody typed, however they typed them.

    "P, S" and "PS" and "p s" are one answer. Only the letters FMCSA defines are taken, so a note
    somebody left in the box does not become a requirement nobody can satisfy."""
    return [c for c in sorted(set((raw or "").upper())) if c in "HNPSTX"]


def usdot_biennial(number: str | None, after: date | None = None) -> date | None:
    """The last day of the month FMCSA's biennial update is due in, for this USDOT number.

    49 CFR 390.19(b): the LAST digit fixes the month - 1 is January through 9 September, 0 is
    October - and the parity of the NEXT-TO-LAST digit fixes the year: odd digit, odd-numbered
    years; even digit, even-numbered years. A single-digit number has no next-to-last digit, which
    reads as zero and so as even.

    Not a count of days from the last filing, which is what this rule used to do. The schedule
    belongs to the number: filing early does not move the deadline, and filing late does not push
    the next one out. A day count drifts further from the real date with every cycle.
    """
    digits = "".join(c for c in str(number or "") if c.isdigit())
    if not digits:
        return None
    month = int(digits[-1]) or 10
    oddyear = bool(int(digits[-2]) % 2) if len(digits) > 1 else False
    after = after or date.today()
    year = after.year
    # The first year on this number's cycle that is not already behind us.
    while True:
        if bool(year % 2) == oddyear:
            due = date(year, month, monthrange(year, month)[1])
            if due >= after:
                return due
        year += 1


def usdot_next_due(number: str | None, filedon: date) -> date | None:
    """When the next biennial update falls due, given that one went in on this day.

    A filing discharges the cycle it belongs to. File in April when the deadline is July of the
    same year and the July deadline is met, so the next one is two years on - which is why this is
    not simply "the next scheduled date after the filing": that would hand back the very deadline
    the filing just answered, and the requirement would read as overdue the day it was satisfied.

    A LATE filing is different. One made in September for a July deadline already missed does not
    buy an extra cycle; the next is the following scheduled date, and that is what falls out of the
    same test, because it lands in a later year than the filing.
    """
    nxt = usdot_biennial(number, filedon + timedelta(days=1))
    if nxt and nxt.year == filedon.year:
        nxt = date(nxt.year + 2, nxt.month, monthrange(nxt.year + 2, nxt.month)[1])
    return nxt


def _determined(finding: str, when) -> str | None:
    """What a bloodborne pathogens exposure determination decided, in a sentence.

    29 CFR 1910.1030(c)(2) is answered either way, and which way it was answered is the whole
    content of the record - it is what decides whether the drivers owe the training. Written
    once here because the sentence is wanted both where a determination has a review date and
    where it has none.
    """
    if finding not in ("exposed", "noexposure") or not when:
        return None
    return f"Determined {when:%m/%d/%Y}: " + (
        "occupational exposure identified, so the drivers in those classifications owe "
        "bloodborne pathogens training." if finding == "exposed"
        else "no occupational exposure identified in these duties.")


def horizon(rule: dict, evidence: dict | None, usdot: str | None = None) -> date | None:
    """The day a record stops counting: its own expiry, or the one the rule's recurrence implies."""
    if not evidence:
        return None
    expires = evidence.get("expireson")
    # Where the rule sets an interval, a date typed onto the record cannot outlast it: a Georgia
    # inspection filed as good for a year is still due six months after it was done (DCH 910.2).
    due = renewed(rule, evidence["effectiveon"]) if evidence.get("effectiveon") else None
    if due and (not expires or due < expires):
        expires = due
    if not expires and rule.get("recurrence") == "usdotbiennial" and evidence.get("effectiveon"):
        expires = usdot_next_due(usdot, evidence["effectiveon"])
    return expires


# 49 CFR 391.51(b)(7)(i): a copy of the certificate the driver gave the State may be used as proof
# of medical certification for up to fifteen days from the day it was ISSUED. It exists because the
# examiner transmits the result to FMCSA, FMCSA passes it to the State and the State posts it to the
# CDLIS record, and none of that is instant. The driver is not in limbo while it happens.
PAPER_STANDS_DAYS = 15


def _cdlis_reading(got: dict, today: date) -> dict:
    """What a CDLIS record says about medical qualification, and how long it stands.

    The order of these tests is the reasoning. A State that says NOT CERTIFIED has answered, and no
    grace period applies to an answer - the fifteen days are for a State that has not caught up,
    not for one that has said no."""
    cert, status = (got.get("selfcert") or ""), (got.get("medcertstatus") or "")
    newcard, oldrecord = got.get("cardissued"), got.get("effectiveon")
    behind = bool(newcard and oldrecord and newcard > oldrecord)
    disagrees = bool(got.get("cardexpires") and got.get("medcertexpires")
                     and got["cardexpires"] != got["medcertexpires"])

    if cert in ("EI", "NA", "EA"):
        # Excepted or intrastate: the State carries no medical status for them, and the certificate
        # in this office's own file is what governs.
        return {"determination": "excepted"}
    if status == "notcertified":
        return {"determination": "notcertified"}
    # The certificate was renewed after this record was pulled, and the State has not caught up.
    # Within the fifteen days the paper stands; the requirement comes due on the day it runs out,
    # which is the day a new record has to be in hand.
    if behind and (status == "notshown" or disagrees):
        until = newcard + timedelta(days=PAPER_STANDS_DAYS)
        if today <= until:
            return {"determination": "paperstands", "expireson": until}
    if status == "notshown":
        # Since 30 January 2015 an absence IS an answer for a non-excepted interstate CDL holder:
        # no medical certification status on the record means not certified. For a driver whose
        # category nobody has recorded, it is a gap rather than a verdict.
        return {"determination": "notcertified" if cert == "NI" else "notshown"}
    if status != "certified":
        return {"determination": None}
    if disagrees:
        return {"determination": "conflict"}
    return {"determination": "certified"}


def deadline(rule: dict, hiredon: date | None, evidence: dict | None = None) -> date | None:
    """The day an obligation of employment first falls due, or None if it is not one.

    A stage on its own is a label. 391.23(d) gives thirty days from the start of employment, and
    without the date to count to there is nothing that can ever be late - the item would sit at
    "nothing on file yet" for a year and the screen would never say otherwise.

    The same is true of the recurring ones before their first turn. 391.25 asks for an inquiry and
    review every twelve months; a driver hired last week is not eleven months late for it, and a
    hard stop saying they may not drive over work that is not owed until next year is simply wrong.
    Once there IS a record, the ordinary expiry arithmetic takes over and this says nothing."""
    stage = rule.get("duestage") or "prehire"
    if not hiredon:
        return None
    if stage == "athire" and rule.get("duedays"):
        return hiredon + timedelta(days=int(rule["duedays"]))
    if stage == "ongoing" and evidence is None:
        return renewed(rule, hiredon)
    return None


def stand(rule: dict, evidence: dict | None, today: date,
          ordered: dict | None = None, usdot: str | None = None) -> tuple[str, str]:
    """The status of one rule for one driver, and the sentence that explains it."""
    if rule.get("evidencekind") == "none":
        return "notapplicable", "This rule removes another one rather than asking for anything."
    if not evidence and ordered and ordered.get("orderedon"):
        return "ordered", f"Sent for on {ordered['orderedon']:%m/%d/%Y}, not back yet."
    if not evidence:
        # A rule with nowhere to file its answer is outstanding work on US, not on the driver, and
        # saying "nothing on file yet" about it would read as their fault and never change.
        if not rule.get("evidencesource"):
            return "pending", "This one applies, but there is nowhere in TripProof to record it yet."
        # And where the rule says WHEN it is owed, say that too. "Nothing on file yet" is true of
        # a thing due next year and of a thing that should have been done before the driver was
        # hired, and a reader cannot tell those apart from four words.
        due = (rule.get("duetext") or "").strip()
        return "pending", f"Nothing on file yet. {due}." if due else "Nothing on file yet."

    finding = (evidence.get("determination") or "").lower()
    # A report the rule asks somebody to read is not answered by the vendor's one-word summary:
    # Georgia's disqualifiers (DCH 914.2.2-914.2.3) are judged from what the report says. A failing
    # result still fails at once; anything else waits until the report has been marked read.
    if (rule.get("reviewrequired") and "reviewstate" in evidence
            and evidence["reviewstate"] != "reviewed" and finding not in FAILING):
        return "review", None
    if finding == "paperstands":
        until = evidence.get("expireson")
        return "expiring", (SAYS["paperstands"]
                            + (f" The copy stands until {until:%m/%d/%Y}." if until else ""))
    if finding == "missing":
        miss = evidence.get("missing") or []
        names = ", ".join(f"{c} ({ENDORSEMENT_NAMES.get(c, c)})" for c in miss)
        one = len(miss) == 1
        return "failed", (
            f"The license on file does not carry the {names} endorsement{'' if one else 's'} this "
            f"work requires. It has to be obtained from the licensing State; a first P, S or H "
            f"endorsement needs entry-level driver training first - 49 CFR Part 380 Subpart F.")
    if finding == "experienced":
        return "satisfied", f'Licensed since {evidence["licensesince"]:%m/%d/%Y}.'
    if finding == "inexperienced":
        return "failed", (f'Licensed since {evidence["licensesince"]:%m/%d/%Y} - less than three '
                          f'years of driving experience.')
    if finding == "unproven":
        return "review", (f'The oldest license on file was issued '
                          f'{evidence["licensesince"]:%m/%d/%Y}, which may be a renewal. Enter the '
                          f'original issue date on the license if the card shows one.')
    if finding == "noincident":
        return "satisfied", "No confirmed wheelchair securement failure on record."
    if finding == "retrained":
        return "satisfied", (f'Retrained in securement on {evidence["trainedon"]:%m/%d/%Y}, after the '
                             f'failure on {evidence["lastfailed"]:%m/%d/%Y}.')
    if finding == "awaitingretraining":
        return "failed", (f'A wheelchair securement failure was confirmed on '
                          f'{evidence["lastfailed"]:%m/%d/%Y}. The driver is removed from service '
                          f'until securement training dated after it is on file.')
    if finding == "withinlimit":
        n = evidence.get("count") or 0
        return "satisfied", ("No at-fault moving violation or accident on record." if not n else
                             "One at-fault moving violation or accident on record. A second "
                             "removes the driver from service.")
    if finding == "removal":
        listed = "; ".join(f'{h["what"]} {h["whenon"]:%m/%d/%Y}' for h in (evidence.get("hits") or [])[:4])
        return "failed", (f'{evidence.get("count")} at-fault moving violations and/or accidents on '
                          f'record ({listed}). The driver must be removed from service.')
    if finding == "newermvr":
        came = evidence.get("newer")
        return "failed", (f"A newer driving record came in{f' on {came:%m/%d/%Y}' if came else ''}. "
                          "The last review does not cover it - complete a new annual review.")
    if finding == "hoursexceeded":
        over = evidence.get("breaches") or []
        said = "; ".join(f'{b["dutydate"]:%m/%d/%Y} - {b["why"]}' for b in over[:3])
        return "failed", (
            "F.A.C. 14-90.006 was exceeded on the work recorded: " + said
            + (f"; and {len(over) - 3} more." if len(over) > 3 else "."))
    if finding == "withinlimits":
        from app import hos
        return "satisfied", (
            f'{evidence.get("days")} days of work recorded, the last on '
            f'{evidence["lastday"]:%m/%d/%Y}. Within every 14-90.006 limit - '
            f'{hos.hours(evidence.get("weektotal"))} on duty in the 7 days ending then, '
            f'against a {hos.hours(hos.WEEK_LIMIT)} limit.')
    if finding == "registerkept":
        n = evidence.get("entries") or 0
        return "satisfied", (
            f"{n} accident{'' if n == 1 else 's'} in the last three years, each recorded with "
            f"everything 49 CFR 390.15(b)(1) asks for." if n else
            "No accident in the last three years. There is nothing to list, which is a register "
            "kept correctly rather than a register missing.")
    if finding == "registershort":
        gaps = evidence.get("short") or []
        return "failed", (
            "49 CFR 390.15(b)(1) asks the register to carry, for each accident, the date, the "
            "city or town and State, the driver, the number injured, the number killed, and "
            "whether hazardous material was released. " + "; ".join(gaps[:3])
            + (f"; and {len(gaps) - 3} more." if len(gaps) > 3 else "."))
    if finding == "numbered":
        return "satisfied", (f'USDOT {evidence.get("usdot")}, operating authority '
                             f'MC-{evidence.get("mcnumber")}.')
    if finding == "noauthority":
        return "failed", (
            f'USDOT {evidence.get("usdot")} is on file, but no FMCSA operating authority number '
            f'is recorded. Carrying passengers for hire across a State line needs authority as '
            f'well as a USDOT number - 49 CFR 365.101. If this company operates only within one '
            f'State, record that it does not drive across a State line (Settings - Company).')
    if finding == "running":
        when = evidence.get("lastdrawn")
        who = evidence.get("issuer")
        return "satisfied", (
            f"A random testing programme is on file{f' with {who}' if who else ''}, and the last "
            f"selection was drawn {when:%m/%d/%Y}." if when else
            "A random testing programme is on file.")
    if finding == "endorsed":
        return "satisfied", ("The license carries every endorsement this work requires: "
                             + ", ".join(evidence.get("needed") or []) + ".")
    # Trained but not yet tested. Not a failure - nobody has done anything wrong - and not
    # satisfied either. The training is on file and the one thing still owed is named.
    if finding == "untested":
        when = evidence.get("effectiveon")
        return "pending", (
            (f"Training recorded {when:%m/%d/%Y}. " if when else "Training recorded. ")
            + SAYS["untested"])
    if finding in FAILING:
        return "failed", evidence.get("said") or SAYS.get(finding, f"The record on file came back {finding}.")
    if finding in REVIEWING:
        return "review", SAYS.get(finding, "A possible match was found - somebody has to settle it.")
    if rule.get("reviewrequired") and finding not in PROVING:
        # Nothing to add to the mark itself: the eye already says it is waiting to be read.
        return "review", None

    expires = horizon(rule, evidence, usdot)
    if expires:
        filed = evidence.get("effectiveon") if finding == "filed" else None
        # A determination's date is the review it set itself, so the sentence has to carry what
        # was determined. "On file until 10/01/2027" is true and says nothing - and what this
        # one decided is what turns the drivers' training on.
        decided = _determined(finding, evidence.get("effectiveon"))
        if expires < today:
            if filed:
                return "expired", (f"Filed with FMCSA on {filed:%m/%d/%Y}. The next was due by "
                                   f"{expires:%m/%d/%Y} and has not been filed.")
            if decided:
                return "expired", f"{decided} It was due to be reviewed by {expires:%m/%d/%Y}."
            return "expired", f"On file, but it ran out on {expires:%m/%d/%Y}."
        if filed:
            said = (f"Filed with FMCSA on {filed:%m/%d/%Y}. The next is due by "
                    f"{expires:%m/%d/%Y}.")
            return ("expiring" if (expires - today).days <= (rule.get("warndays") or WARN_DAYS)
                    else "satisfied"), said
        soon = (expires - today).days <= (rule.get("warndays") or WARN_DAYS)
        if decided:
            return ("expiring" if soon else "satisfied"), \
                   f"{decided} Next review {expires:%m/%d/%Y}."
        if soon:
            return "expiring", f"On file until {expires:%m/%d/%Y}."
        return "satisfied", f"On file until {expires:%m/%d/%Y}."
    if finding in SAYS:
        return "satisfied", SAYS[finding]
    if evidence.get("exempt"):
        return "satisfied", "Recorded as exempt."
    when = evidence.get("effectiveon")
    # A policy is adopted, not filed. The line says which act happened and on what day, because
    # "on file" is true of the published template for every company on the day they sign up.
    if finding == "adopted" and when:
        return "satisfied", f"Adopted by this company, effective {when:%m/%d/%Y}."
    if finding == "filed" and when:
        return "satisfied", f"Filed with FMCSA on {when:%m/%d/%Y}."
    if finding == "inspected" and when:
        return "satisfied", (f"Last inspection report {when:%m/%d/%Y}. No defect outstanding.")
    if finding in ("exposed", "noexposure") and when:
        return "satisfied", _determined(finding, when)
    if finding == "trained" and when:
        return "satisfied", (f"Every appointed supervisor is trained. The earliest training on "
                             f"file is dated {when:%m/%d/%Y}.")
    if finding == "registered":
        looked = evidence.get("lastverifiedon") or when
        return "satisfied", (f"Registered with FMCSA, verified {looked:%m/%d/%Y}." if looked
                             else "Registered with FMCSA.")
    return "satisfied", f"On file, dated {when:%m/%d/%Y}." if when else "On file."


def _company_evidence(conn: Connection, accountid: str, source: str | None,
                      code: str | None = None) -> dict | None:
    """The record that answers one company requirement.

    Far simpler than a driver's: a company obligation is a document the company holds - a policy,
    a certificate, an agreement, a registration - so there is one place to look. Where a company
    rule ever needs something cleverer it gets a branch here, the way the driver's evidence does.
    """
    if not source:
        return None
    kind, _, which = source.partition(":")
    if kind == "companyrole":
        # A role somebody holds, not a document somebody filed. Answered by the appointment itself,
        # which is why the evidence carries the day it was made rather than a document id.
        return row(conn, """
            SELECT r.recordid, r.since AS effectiveon, r.until AS expireson, 0 AS exempt,
                   NULL AS documentid, 'companyroles' AS sourcetable, 'qualified' AS determination
            FROM companyroles r JOIN users u ON u.recordid = r.userid
            WHERE r.accountid = :a AND r.role = :role AND r.until IS NULL
              AND u.deleted IS NULL
            ORDER BY r.since DESC LIMIT 1
        """, a=accountid, role=which)
    if kind == "accidentregister":
        # 49 CFR 390.15(b). The register is not a document anybody files - it is a list the
        # carrier keeps, and 390.15(b)(1) says what each entry must carry: the date, the city or
        # town and State, the driver, how many were injured, how many died, and whether hazardous
        # material other than fuel from the vehicles' own tanks was released.
        #
        # So the question is not "is there a register" - it is whether the accidents on it are
        # recorded completely. An empty register is a complete register: a carrier with no
        # accidents in three years has nothing to list and is keeping the list correctly.
        since = date.today() - timedelta(days=3 * 365)
        held = rows(conn, """
            SELECT a.recordid, a.occurredon, a.location, a.fatalities, a.injuries,
                   a.hazmatreleased, d.firstname, d.lastname
            FROM driveraccidents a
              LEFT JOIN drivers d ON d.recordid = a.driverid
            WHERE a.accountid = :a AND a.withdrawn IS NULL
              AND (a.occurredon IS NULL OR a.occurredon >= :since)
            ORDER BY a.occurredon DESC
        """, a=accountid, since=since)
        short = []
        for x in held:
            missing = [w for w, ok in (("the date", x["occurredon"]),
                                       ("where it happened", (x["location"] or "").strip()),
                                       ("the driver", x["firstname"]),
                                       ("the number injured", x["injuries"] is not None),
                                       ("the number killed", x["fatalities"] is not None),
                                       ("whether hazardous material was released",
                                        x["hazmatreleased"] is not None)) if not ok]
            if missing:
                when = f'{x["occurredon"]:%m/%d/%Y}' if x["occurredon"] else "an undated accident"
                short.append(f'{when} is missing {", ".join(missing)}')
        return {"recordid": accountid, "effectiveon": None, "expireson": None, "exempt": 0,
                "documentid": None, "sourcetable": "driveraccidents",
                "entries": len(held), "short": short,
                "determination": "registershort" if short else "registerkept"}

    if kind == "usdotnumber":
        # The number everything else is filed against. Held on the account rather than as a
        # document, because that is where every other part of TripProof reads it from - the
        # MCS-150 schedule is computed from its last two digits.
        got = row(conn, "SELECT usdot, mcnumber FROM accounts WHERE recordid = :a", a=accountid)
        if not got or not (got.get("usdot") or "").strip():
            return None
        return {"recordid": accountid, "effectiveon": None, "expireson": None, "exempt": 0,
                "documentid": None, "sourcetable": "accounts",
                "usdot": got["usdot"], "mcnumber": (got.get("mcnumber") or "").strip(),
                "determination": "numbered" if (got.get("mcnumber") or "").strip()
                                 else "noauthority"}

    if kind == "exposuredetermination":
        # 29 CFR 1910.1030(c)(2). The determination in force, and only if it was certified -
        # an uncertified one is a draft, and the section asks for the employer's determination,
        # not for somebody's working notes.
        #
        # It is satisfied either way. A company that determined there is NO occupational
        # exposure has made the determination the section asks for, and it is the one an
        # inspector wants to see from a carrier saying 1910.1030 does not reach it.
        got = row(conn, """
            SELECT d.recordid, d.assessedon AS effectiveon, d.nextreview AS expireson,
                   0 AS exempt, NULL AS documentid, 'exposuredeterminations' AS sourcetable,
                   CASE WHEN d.exposed THEN 'exposed' ELSE 'noexposure' END AS determination
            FROM exposuredeterminations d
            JOIN documentsignatures s
              ON s.accountid = d.accountid AND s.ownertype = 'exposure'
             AND s.ownerid = d.recordid AND s.doctype = 'BBP_EXPOSURE_DETERMINATION'
            WHERE d.accountid = :a AND d.withdrawn IS NULL
            ORDER BY d.assessedon DESC, d.added DESC LIMIT 1
        """, a=accountid)
        return got
    if kind == "supervisortraining":
        # 49 CFR 382.603 trains PEOPLE, so this is answered by the appointments - and by each
        # of those people having SIGNED for their own training, not by somebody in the office
        # recording minutes on their behalf.
        #
        # That was the earlier reading and it was the wrong one. The person who decides whether
        # a driver is sent for a reasonable suspicion test is the person the section is about,
        # and a row saying they did two hours, entered by their manager, is an assertion about
        # them rather than by them. The record they sign carries the durations on its face.
        #
        # The requirement stands on the whole supervisory staff: one supervisor who has signed
        # beside three who have not is not a trained supervisory staff, so the oldest training
        # among them is what dates it and any gap means no evidence at all.
        #
        # The date is the day the training was done, not the day the record was signed. The
        # supervisor states both as one act, so they come from one place; a company trained in
        # September does not become trained in October because that is when somebody sat down
        # to sign for it.
        held = rows(conn, """
            SELECT u.name, d.signedon, t.completedon
            FROM companyroles r
              JOIN users u ON u.recordid = r.userid
              LEFT JOIN documentsignatures d
                ON d.accountid = r.accountid AND d.ownertype = 'user' AND d.ownerid = r.userid
               AND d.doctype = 'SUPERVISOR_TRAINING_RECORD'
              LEFT JOIN supervisortraining t
                ON t.accountid = r.accountid AND t.userid = r.userid AND t.deleted IS NULL
            WHERE r.accountid = :a AND r.role = 'supervisor' AND r.until IS NULL
              AND u.deleted IS NULL
        """, a=accountid)
        if not held or any(h["signedon"] is None for h in held):
            return None
        dated = [h["completedon"] or h["signedon"].date() for h in held]
        return {"recordid": accountid, "effectiveon": min(dated),
                "expireson": None, "exempt": 0, "documentid": None,
                "sourcetable": "documentsignatures", "determination": "trained"}
    if kind == "randomselections":
        return row(conn, """
            SELECT recordid, drawnon AS effectiveon, NULL AS expireson, 0 AS exempt, documentid,
                   'randomselections' AS sourcetable, NULL AS determination
            FROM randomselections
            WHERE accountid = :a AND deleted IS NULL
            ORDER BY drawnon DESC, added DESC LIMIT 1
        """, a=accountid)
    if kind == "clearinghouse":
        # The state of an account at FMCSA, not a document. A row that says "not registered" is an
        # answer and is treated as one; no row at all is nobody having looked.
        got = row(conn, """
            SELECT accountid AS recordid, verifiedon AS effectiveon, NULL AS expireson,
                   0 AS exempt, documentid, 'clearinghouseregistration' AS sourcetable,
                   registered, queryplan, lastverifiedon
            FROM clearinghouseregistration WHERE accountid = :a
        """, a=accountid)
        if not got or got["registered"] is None:
            return None
        if not got["registered"]:
            return {**got, "determination": "notregistered"}
        # Registered but with no query plan cannot run the queries the registration exists for.
        return {**got, "determination": "registered" if got["queryplan"] else "noqueryplan"}
    if kind == "mcs150":
        # The biennial update, answered by the day it went in. No expiry of its own: when the next
        # one is due is read off the USDOT number, never off this record.
        return row(conn, """
            SELECT recordid, filedon AS effectiveon, NULL AS expireson, 0 AS exempt, documentid,
                   'mcs150filings' AS sourcetable, 'filed' AS determination
            FROM mcs150filings
            WHERE accountid = :a AND deleted IS NULL
            ORDER BY filedon DESC, added DESC LIMIT 1
        """, a=accountid)
    if kind == "policy":
        # A policy TripProof publishes and the company adopts. The act is the adoption - an
        # effective date this company set for THIS policy - because the template existing is true
        # of everybody from the first day and is no act of theirs. The requirement's own code is
        # tried as a document too, so a company that uploaded its policy before these became
        # templates keeps what it filed.
        adopted_on = row(conn, """
            SELECT code AS recordid, effectiveon, NULL AS expireson, 0 AS exempt,
                   NULL AS documentid, 'companypolicies' AS sourcetable,
                   'adopted' AS determination
            FROM companypolicies
            WHERE accountid = :a AND code = :c AND effectiveon IS NOT NULL
        """, a=accountid, c=which)
        if adopted_on:
            return _random_programme(conn, accountid, code, adopted_on)
        which = code or which
    elif kind != "credential":
        return None
    got = _credential_life(row(conn, """
        SELECT c.recordid, c.issuedon AS effectiveon, c.expireson, c.exempt, c.documentid,
               c.issuer, t.maxagedays, t.defaultvaliddays,
               'credentials' AS sourcetable, NULL AS determination
        FROM credentials c JOIN credentialtypes t ON t.recordid = c.credentialtypeid
        WHERE c.accountid = :a AND c.subject = 'company' AND c.subjectid = :a AND t.code = :code
          AND c.deleted IS NULL AND c.revokedon IS NULL
        ORDER BY c.issuedon DESC, c.added DESC LIMIT 1
    """, a=accountid, code=which))
    return _random_programme(conn, accountid, code, got)


def _random_programme(conn: Connection, accountid: str, code: str | None,
                      got: dict | None) -> dict | None:
    """49 CFR 382.305 is a rate met across a year, not a document held in a drawer.

    Applied to whatever answered the requirement, not to one kind of answer. It used to sit at
    the end of the credential branch only, so the day the programme became a policy the carrier
    adopts instead of a file it uploads, "adopted and never drawn from" would have started
    reading as satisfied - the one state this check exists to catch."""
    if not got or code != "RANDOM_TESTING_PROGRAM":
        return got
    drawn = row(conn, "SELECT MAX(drawnon) AS lastdrawn FROM randomselections "
                      "WHERE accountid = :a AND deleted IS NULL", a=accountid) or {}
    last = drawn.get("lastdrawn")
    stale = not last or (date.today() - last).days > 365
    return {**got, "lastdrawn": last, "determination": "nodraws" if stale else "running"}


def _vehicle_evidence(conn: Connection, accountid: str, vehicleid: str,
                      source: str | None) -> dict | None:
    """The record that answers one vehicle requirement."""
    if not source:
        return None
    kind, _, which = source.partition(":")
    if kind == "dvir":
        # What settles this is not the newest report but the OLDEST defect nobody has corrected:
        # 49 CFR 396.11(c) stops the vehicle until it is put right, and a clean report filed
        # afterwards does not lift it. Where nothing is open, the latest report is the evidence.
        open_defect = row(conn, """
            SELECT recordid, reportedon AS effectiveon, NULL AS expireson, 0 AS exempt, documentid,
                   'vehicledvirs' AS sourcetable, 'opendefect' AS determination, defectnote
            FROM vehicledvirs
            WHERE accountid = :a AND vehicleid = :v AND deleted IS NULL
              AND defects = 1 AND correctedon IS NULL
            ORDER BY reportedon ASC, added ASC LIMIT 1
        """, a=accountid, v=vehicleid)
        if open_defect:
            return open_defect
        return row(conn, """
            SELECT recordid, reportedon AS effectiveon, NULL AS expireson, 0 AS exempt, documentid,
                   'vehicledvirs' AS sourcetable, 'inspected' AS determination
            FROM vehicledvirs
            WHERE accountid = :a AND vehicleid = :v AND deleted IS NULL
            ORDER BY reportedon DESC, added DESC LIMIT 1
        """, a=accountid, v=vehicleid)
    if kind == "maintenance":
        return row(conn, """
            SELECT recordid, performedon AS effectiveon, NULL AS expireson, 0 AS exempt, documentid,
                   'vehiclemaintenance' AS sourcetable, NULL AS determination
            FROM vehiclemaintenance
            WHERE accountid = :a AND vehicleid = :v AND deleted IS NULL
            ORDER BY performedon DESC, added DESC LIMIT 1
        """, a=accountid, v=vehicleid)
    if kind != "credential":
        return None
    return _credential_life(row(conn, """
        SELECT c.recordid, c.issuedon AS effectiveon, c.expireson, c.exempt, c.documentid,
               t.maxagedays, t.defaultvaliddays,
               'credentials' AS sourcetable, NULL AS determination
        FROM credentials c JOIN credentialtypes t ON t.recordid = c.credentialtypeid
        WHERE c.accountid = :a AND c.subject = 'vehicle' AND c.subjectid = :v AND t.code = :code
          AND c.deleted IS NULL AND c.revokedon IS NULL
        ORDER BY c.issuedon DESC, c.added DESC LIMIT 1
    """, a=accountid, v=vehicleid, code=which))


def for_vehicle(conn: Connection, accountid: str, vehicleid: str, facts: dict,
                today: date | None = None) -> list[dict]:
    """What is asked of one VEHICLE, and where it stands on each of it.

    The same catalog, the same stages, gates and expiry arithmetic as a driver's or a company's -
    only the subject differs. Written as its own function for the same reason `for_company` is:
    almost nothing in the driver's version applies, and what matters is the part they share, which
    is how a rule becomes a status."""
    today = today or date.today()
    elected = adopted(conn, accountid)
    out = []
    for rule in rows(conn, """
        SELECT recordid, accountid, code, name, description, authoritytype, authority, citation,
               applieswhen, evidencekind, evidencesource, blocking, gate, grouping, duestage,
               duetext, recurrence, recurrencedays, recurrencemonths, warndays, note, sortorder,
               program, offered
        FROM compliancerules
        WHERE subject = 'vehicle' AND effectiveto IS NULL
          AND (accountid IS NULL OR accountid = :a)
        ORDER BY sortorder, name
    """, a=accountid):
        reaches = applies(condition(rule["applieswhen"]), facts)
        # A rule TripProof offers reaches no vehicle until the company adopts it, as for drivers.
        offeredonly = rule["offered"] and rule["code"] not in elected
        if offeredonly:
            status, why, evidence = "notapplicable", (
                "Offered as a company requirement. Nothing asks it of this vehicle until this "
                "company adopts it."), None
            reaches = False
        elif reaches is False:
            status, why, evidence = "notapplicable", "Does not reach this vehicle.", None
        elif reaches is None:
            waiting = unanswered(condition(rule["applieswhen"]), facts)
            status = "unknown"
            why = "; ".join(dict.fromkeys(UNANSWERED.get(f, f) for f in waiting))
            evidence = None
        else:
            evidence = _vehicle_evidence(conn, accountid, vehicleid, rule["evidencesource"])
            status, why = stand(rule, evidence, today)
        out.append({**{k: rule[k] for k in ("code", "name", "description", "authoritytype",
                                            "authority", "citation", "duestage", "duetext",
                                            "blocking", "gate", "grouping", "note", "evidencekind",
                                            "evidencesource", "recurrence", "recurrencedays",
                                            "recurrencemonths", "program", "offered")},
                    "scheduled": bool(rule.get("scheduled")),
                    "own": rule["accountid"] is not None,
                    "applies": reaches, "status": status, "why": why,
                    "documentid": (evidence or {}).get("documentid"),
                    "on": (evidence or {}).get("effectiveon"),
                    "expireson": horizon(rule, evidence)})
    return out


def for_company(conn: Connection, accountid: str, facts: dict,
                today: date | None = None) -> list[dict]:
    """What is asked of the COMPANY, and where it stands on each of it.

    The same catalog, the same stages, the same gates and the same expiry arithmetic as a driver's
    requirements - only the subject differs. Written as its own function rather than a parameter on
    for_driver because almost nothing in there applies: a company has no hire date, no license, no
    drug and alcohol standing and nobody to send a document to. What it shares is the part that
    matters, which is how a rule becomes a status.
    """
    today = today or date.today()
    usdot = (row(conn, "SELECT usdot FROM accounts WHERE recordid = :a", a=accountid)
             or {}).get("usdot")
    out = []
    for rule in rows(conn, """
        SELECT recordid, accountid, code, name, description, authoritytype, authority, citation,
               applieswhen, evidencekind, evidencesource, blocking, gate, grouping, duestage,
               duetext, recurrence, recurrencedays, recurrencemonths, warndays, note, sortorder, offered,
               retentionrule
        FROM compliancerules
        WHERE subject = 'company' AND effectiveto IS NULL
          AND (accountid IS NULL OR accountid = :a)
        ORDER BY sortorder, name
    """, a=accountid):
        reaches = applies(condition(rule["applieswhen"]), facts)
        if reaches is False:
            status, why, evidence = "notapplicable", "Does not reach this company.", None
        elif reaches is None:
            waiting = unanswered(condition(rule["applieswhen"]), facts)
            status = "unknown"
            why = "; ".join(dict.fromkeys(UNANSWERED.get(f, f) for f in waiting))
            evidence = None
        else:
            evidence = (_company_evidence(conn, accountid, rule["evidencesource"], rule["code"])
                        or _filed(conn, accountid, accountid, rule["recordid"], "company"))
            status, why = stand(rule, evidence, today, usdot=usdot)
            # A schedule read off a number cannot be read without the number. Said plainly rather
            # than letting the requirement sit there looking answered.
            if rule.get("recurrence") == "usdotbiennial" and not usdot:
                status = "unknown"
                why = ("Nobody has recorded this company's USDOT number, so FMCSA's biennial "
                       "schedule cannot be worked out (Company - Operations).")
            elif rule["evidencesource"] == "exposuredetermination" and not evidence:
                why = ("No exposure determination has been made. 29 CFR 1910.1030(c)(2) asks "
                       "for one either way - whether or not these duties involve exposure - "
                       "and until it exists nobody can say whether the drivers owe bloodborne "
                       "pathogens training.")
            elif rule["evidencesource"] == "supervisortraining" and not evidence:
                # Read from the same place the evidence above is read from. Naming who has not
                # signed means asking about signatures, and an explanation that went looking in
                # supervisortraining would be a second copy of the question, free to disagree
                # with the answer it is explaining.
                appointed = rows(conn, """
                    SELECT u.name, d.signedon
                    FROM companyroles r
                      JOIN users u ON u.recordid = r.userid
                      LEFT JOIN documentsignatures d
                        ON d.accountid = r.accountid AND d.ownertype = 'user'
                       AND d.ownerid = r.userid AND d.doctype = 'SUPERVISOR_TRAINING_RECORD'
                    WHERE r.accountid = :a AND r.role = 'supervisor' AND r.until IS NULL
                      AND u.deleted IS NULL
                    ORDER BY u.name
                """, a=accountid)
                waiting = [h["name"] for h in appointed if h["signedon"] is None]
                why = (("No supervisor has been appointed, so nobody in this company may determine "
                        "reasonable suspicion.") if not appointed
                       else ("Not signed by " + ", ".join(waiting)
                             + ". A record somebody else fills in is not the supervisor saying "
                               "they were trained.") if waiting
                       else "No signed training record is on file.")
            elif rule.get("evidencekind") == "registration" and not evidence:
                why = ("Not verified. Registration is done electronically at the FMCSA "
                       "Clearinghouse - there is no form to file - so record the employer account "
                       "here once it exists.")
            elif rule.get("recurrence") == "usdotbiennial" and not evidence:
                # The deadline belongs to the number, so it exists whether or not anything has
                # ever been recorded here. Saying only "nothing on file" withholds the date.
                falls = usdot_biennial(usdot, today)
                why = (f"No filing recorded. The next update is due by {falls:%m/%d/%Y}."
                       if falls else why)
        out.append({**{k: rule[k] for k in ("code", "name", "description", "authoritytype",
                                            "authority", "citation", "duestage", "duetext",
                                            "blocking", "gate", "grouping", "note", "evidencekind",
                                            "evidencesource", "recurrence", "recurrencedays",
                                            "recurrencemonths")},
                    "scheduled": bool(rule.get("scheduled")),
                    "own": rule["accountid"] is not None,
                    "applies": reaches, "status": status, "why": why,
                    "documentid": (evidence or {}).get("documentid"),
                    "on": (evidence or {}).get("effectiveon"),
                    "expireson": horizon(rule, evidence, usdot)})
    return out


# Two rules are about the FILE rather than about anything that can be put in it, and both sat
# saying "there is nowhere in TripProof to record it yet". There is nowhere because there is
# nothing to record: 49 CFR 391.51 asks whether a qualification file exists holding the things
# Subpart C requires, and TripProof IS that file. So they are answered by the rest of the list.
# Requirements that are about a driver's fitness for safety-sensitive work, and so cannot read
# as met while that driver is barred from it. Not every testing rule belongs here: whether the
# pre-employment test was collected is a question about an event, and it stays answered.
PROHIBITION_FOLLOWS = ("FL_TD_DRUG_TESTING",)

DERIVED = {
    "FL_INTRASTATE_FULL": ("49 CFR", "Everything the federal rules ask of this driver is on file."),
}


def _derive_file_rules(out: list[dict]) -> list[dict]:
    """Answer the rules that ask about the file as a whole, from the file as a whole."""
    for item in out:
        want = DERIVED.get(item["code"])
        if not want or item["applies"] is not True:
            continue
        prefix, good = want
        # What this rule is about: the other requirements under the same authority that actually
        # reach this driver. Named individually when they are short, because "incomplete" is not
        # something anybody can act on.
        others = [o for o in out
                  if o["code"] != item["code"] and o["applies"] is True
                  and (o.get("citation") or "").startswith(prefix)]
        short = [o for o in others if o["status"] not in ("satisfied", "expiring", "derived")]
        if not others:
            item["status"], item["why"] = "unknown", (
                "Nothing else under this authority reaches this driver, so there is nothing for "
                "the file to hold.")
        elif short:
            item["status"] = "pending"
            item["why"] = ("Waiting on " + ", ".join(o["name"] for o in short[:4])
                           + (f" and {len(short) - 4} more." if len(short) > 4 else "."))
        else:
            item["status"], item["why"] = "satisfied", good
    return out


def for_driver(conn: Connection, accountid: str, driverid: str, facts: dict,
               today: date | None = None) -> list[dict]:
    """Every driver rule in force, what it asks of this driver, and where they stand on it."""
    today = today or date.today()
    unchecked = awaiting_review(conn, accountid, driverid)
    read = already_read(conn, accountid, driverid)
    # A reading lives in one of two places depending on how the paper arrived: against the upload
    # request for something the driver sent in, against the record for everything else. The gate
    # consults both, because the act is the same act.
    readdocs = read_documents(conn, accountid, driverid)
    elected = adopted(conn, accountid)
    unread = answered_unread(conn, accountid, driverid)
    # Every fact those unread submissions carried, so each requirement standing on one of them
    # waits for the same reading rather than only the requirement that was asked for by name.
    unreadfacts = {f for code in unread for f in ANSWERS.get(code, ())}
    chased = asked_of_driver(conn, accountid, driverid)
    # The day employment started, which is what every after-hire deadline counts from.
    hired = row(conn, "SELECT hiredon FROM drivers WHERE recordid = :d AND accountid = :a",
                d=driverid, a=accountid)
    hiredon = (hired or {}).get("hiredon")
    # The most recent drug and alcohol violation on file, cleared or not. The Clearinghouse is the
    # register OF these, so a query run before one cannot have been answering about it - see
    # `violationresets` below. Cleared bars count: a violation that happened still happened, and
    # what matters is only whether the query came after it.
    worst = row(conn, """SELECT MAX(startedon) AS whenon FROM driverprohibitions
                        WHERE accountid = :a AND driverid = :d AND withdrawn IS NULL""",
                a=accountid, d=driverid)
    violatedon = (worst or {}).get("whenon")
    out = []
    for rule in rows(conn, """
        SELECT recordid, code, name, authoritytype, authority, citation, applieswhen, evidencekind,
               qualificationcode, authoritycategory, enforcement, legalreview, program,
               accountid, evidencesource, origin, extendable, extendnote, offered,
               alternatesource, alternatewhen, reviewrequired, determination,
               violationresets,
               blocking, gate, grouping, duestage, duedays, duetext, recurrence, recurrencedays, recurrencemonths,
               scheduled, warndays, note, sortorder
        FROM compliancerules
        WHERE subject = 'driver' AND effectiveto IS NULL
          -- Ours, plus this company's own. A requirement one operator wrote is invisible to every
          -- other one, and our migrations never touch it.
          AND (accountid IS NULL OR accountid = :acct)
        ORDER BY sortorder, name
    """, acct=accountid) + contract_rules(conn, accountid):
        expr = condition(rule["applieswhen"])
        reaches = applies(expr, facts)
        # A rule TripProof offers rather than imposes. No regulation puts it in force, so it
        # reaches nobody until this company adopts it - which the next few lines then do. Said
        # here rather than by giving it a condition that is always false, so the file can tell a
        # rule nobody has turned on from a rule whose condition did not reach this driver.
        if rule.get("offered"):
            reaches = False
        # Who is asking. The regulation, until the regulation does not reach this driver and the
        # company has adopted the rule anyway - and never the other way round: an election cannot
        # switch off something the law requires, so this only ever looks at a rule the regulation
        # has already declined to reach.
        because, asking = "regulation", None
        choice = elected.get(rule["code"]) or {}
        # Who the COMPANY asks it of, where the regulation does not. "Every driver" is not the only
        # honest answer: a company may want a check on the drivers the federal programme does not
        # already cover, or only on the commercial ones, and saying so is not the same as saying
        # everybody. An election still cannot switch OFF what the law requires - this only ever
        # looks at a rule the regulation has already declined to reach.
        WIDER = {
            "alldrivers": True,
            "cdl": facts.get("driver.cdl") is True,
            "noncdl": facts.get("driver.cdl") is False,
        }
        if reaches is not True and rule["extendable"] and WIDER.get(choice.get("applyto")):
            reaches, because, asking = True, "company", choice.get("reason")
        if reaches is False:
            status = "notapplicable"
            said = "; ".join(dict.fromkeys(explain_false(expr, facts)))
            why = ("Offered as a company requirement. Nothing asks it of this driver until this "
                   "company adopts it (Company - Driver Qualifications)."
                   if rule.get("offered") else
                   f"Does not reach this driver - {said}." if said else "Does not reach this driver.")
            evidence = None
        elif reaches is None:
            status = "unknown"
            waiting = unanswered(expr, facts)
            why = "; ".join(dict.fromkeys(UNANSWERED.get(f, f) for f in waiting))
            evidence = None
        else:
            evidence = (_evidence(conn, accountid, driverid, rule["evidencesource"], facts)
                        or _filed(conn, accountid, driverid, rule["recordid"]))
            # Some rules may be answered by evidence kept for another one, but only while a condition
            # holds - F.A.C. 14-90.0041 lets one examination answer both the federal and the Florida
            # medical requirement where the system has adopted qualifying alternative standards.
            # Two requirements, one physical. The rules stay separate; the evidence is shared, and
            # only where the company has said the condition is met.
            instead = None
            if evidence is None and rule["alternatesource"]:
                if applies(condition(rule["alternatewhen"]), facts) is True:
                    evidence = _evidence(conn, accountid, driverid, rule["alternatesource"])
                    instead = rule["alternatesource"] if evidence else None
            # A record that predates a violation is not a stale answer, it is an answer to a
            # different question. The Clearinghouse holds the violations; a query run the week
            # before one was recorded says nothing about it however recently it was run, and
            # letting it stand would requalify a driver on a document that cannot speak to the
            # thing that disqualified them. Dropped rather than failed: nothing is wrong with the
            # old query, there simply is not one that answers this yet.
            if (rule.get("violationresets") and evidence and violatedon
                    and evidence.get("effectiveon") and evidence["effectiveon"] < violatedon):
                evidence, instead = None, None
            waiting_on = None if evidence else _ordered(conn, accountid, driverid, rule["evidencesource"])
            status, why = stand(rule, evidence, today, waiting_on)
            # On file and in date, but nobody can say where the screening came from. It stands
            # under review until somebody records that it came from the authority itself.
            if (evidence or {}).get("determination") == "noprovenance" and status in (
                    "satisfied", "expiring"):
                status, why = "review", ("On file, but it does not say it came from the FDLE or "
                                         "the AHCA Clearinghouse. Record where it came from.")
            # ANYTHING FROM OUTSIDE IS UNREAD UNTIL SOMEBODY HERE READS IT.
            #
            # One rule, applied once, rather than a special case per kind of thing. Whatever else a
            # requirement says, it does not go green on something this office has not looked at -
            # it is on file and it is waiting on us, which is its own state.
            #
            # Three ways of recognising it, and the third is the one that cannot be forgotten.
            #
            # The first two spot a thing by the route it took - the document it brought, or the
            # request it answered - and a route is something a new feature can fail to go down. The
            # third asks the rule itself where its evidence comes from, so a requirement whose
            # evidence is made outside this office is unread from the moment the record exists,
            # whoever filed it and however it got here. There is no path to forget.
            #
            # A record carrying its own reading already counts as read - an MVR with a finding, a
            # report with an outcome, a road test with a result - so nothing that already had a way
            # of being marked read needs a second one.
            outside = needs_reading(rule, evidence, read, readdocs)
            arrived = (evidence and evidence.get("documentid") in unchecked) \
                or _asked_code(rule) in unread or outside
            if arrived and status in ("satisfied", "expiring", "pending", "failed", "expired"):
                status = "review"
                why = None          # the eye already says it is waiting to be read
            # A requirement ABOUT somebody's fitness for safety-sensitive work cannot read as
            # met while that person is barred from safety-sensitive work. The records exist and
            # the tests were done - which is why the evidence says satisfied - but the question
            # F.A.C. 41-2.006(4)(a) is asking is whether this driver is good for the work, and
            # today the answer is no. The bar itself is DA_PROHIBITION; this stops the row
            # beside it contradicting it.
            if (rule["code"] in PROHIBITION_FOLLOWS and facts.get("driver.prohibited") is True
                    and status in ("satisfied", "expiring", "pending")):
                status, why = "failed", (
                    "This driver is removed from safety-sensitive functions, so nothing here "
                    "qualifies them for it. The records themselves are on file - see Removed "
                    "from safety-sensitive functions for the bar and what lifts it.")
            if instead:
                # Which record is doing the work, named rather than implied - the file has to say
                # what answered a requirement, not merely that something did.
                why = f"{why} {ANSWERED_BY.get(instead, 'Answered by evidence held elsewhere.')}"
            # Asked of the driver and not back yet. The office's own instruction: a request in
            # flight shows as waiting even where something is already on file, because what is on
            # file is the thing being replaced. Only a worse state outranks it - an expired record
            # or an adverse finding is not made better by having asked for a new one.
            if status in ("pending", "satisfied", "expiring"):
                kind_, _, which_ = (rule["evidencesource"] or "").partition(":")
                code_ = "DRIVER_LICENSE" if kind_ == "licensecopy" else which_
                waiting_for = chased.get(code_)
                if waiting_for:
                    asked_on = f'{waiting_for["askedon"]:%m/%d/%Y}'
                    why = (f'{why} Asked of the driver again on {asked_on}, not back yet.'
                           if status != "pending"
                           else f'Asked of the driver on {asked_on}, not back yet.')
                    status = "ordered"
            # 49 CFR 391.23(a)(1) and 391.25(a) both ask for a record from EVERY licensing authority
            # the driver held a license in - so a rule answered by one record is not answered until
            # every state is covered. Without this a driver with a Delaware license and a Florida
            # one reads as complete on the Florida record alone.
            # Answered by what the applicant said on their own application, under their own
            # signature. Two different questions are being asked of such an answer, and they are
            # not the same rule:
            #
            #   applicationanswered:  did they answer it at all? Either answer completes it.
            #   applicationanswer:    is the answer yes? A no is a failure of the rule.
            #
            # The 40.25(j) questionnaire is the first kind - disclosing a violation completes the
            # questionnaire, it does not fail it. The return-to-duty rule it triggers is the second.
            source_ = rule["evidencesource"] or ""
            # A paper copy filed against the rule answers it too: the office may hold a completed
            # form that never went through this software, and that is still the answer.
            if evidence is None and (source_.startswith("applicationanswered:")
                                     or source_.startswith("applicationanswer:")):
                kind_, _, fact_ = source_.partition(":")
                said = facts.get(f"driver.{fact_}")
                if said is None:
                    status, why = "pending", "Not answered on the application yet."
                elif kind_ == "applicationanswered":
                    status, why = "satisfied", (
                        "Disclosed on the application." if said else "Answered on the application.")
                elif said:
                    # An applicant's own account of something done elsewhere raises the question
                    # and does not close it. Where the rule asks for a reading, what closes it is
                    # paper somebody in this office has in their hand.
                    if rule.get("reviewrequired"):
                        status, why = "review", ("The driver says this is complete. Nothing "
                                                 "documenting it has been filed.")
                    else:
                        status, why = "satisfied", "Confirmed on the application."
                else:
                    status, why = "failed", "The driver says this is not complete."
                # An answer that came down a link is no more read than a document that did. It
                # behaves exactly as a medical certificate or a license does coming back from the
                # driver: on file, waiting on us, and not green until somebody says they read it.
                if status == "satisfied" and fact_ in unreadfacts:
                    # Nothing to add to the mark: the eye already says it is waiting to be read.
                    status, why = "review", None
            if (rule["evidencesource"] or "").startswith("mvr"):
                # How long one of these stands is the rule's own arithmetic - the same sum stand()
                # does above, asked once per state. A record pulled once under 391.23(a)(1) has no
                # horizon; one the rule says recurs goes out of date on schedule.
                got = mvrs.coverage(
                    conn, accountid, driverid, today=today, window=mvrs.HIRE_LOOKBACK,
                    lapses=mvrs.horizon(rule))
                # The states ARE the rule, so they decide the mark rather than adjusting one
                # taken from a single record. A rule answered by one record read as complete on
                # that record alone, whatever the other states said.
                overall = mvrs.standing(got, today)
                if overall:
                    status, why = overall
            # 391.23(d) and (e) are answered employer by employer, and 391.23(i) says the asking
            # counts where the answer never comes. So the mark is the state of the inquiries, not
            # whether some document exists.
            elif (rule["evidencesource"] or "") == "employerhistory":
                status, why = _employer_standing(
                    employers.for_driver(conn, accountid, driverid))
        # An after-hire obligation that has run past its date. Not a bad result and not an expiry -
        # nothing came back wrong and nothing ran out - but it is no longer merely outstanding, and
        # a screen that keeps calling it "nothing on file yet" in week six is not telling anybody
        # what has happened.
        if rule.get("evidencekind") == "fact" and not evidence and status == "pending":
            want = (rule["evidencesource"] or "").partition(":")[2]
            why = UNANSWERED.get(want, why)
        if (rule.get("violationresets") and violatedon and not evidence
                and status == "pending"):
            why = (f"The last query was run before the violation of "
                   f"{violatedon:%m/%d/%Y}. Run a new one.")
        dueon = deadline(rule, hiredon, evidence)
        if dueon and today > dueon and status in ("pending", "ordered", "unknown"):
            status = "overdue"
            why = f"Was due by {dueon:%m/%d/%Y}."
        elif dueon and status == "pending":
            # Not outstanding: owed, and not yet. The date is the whole of what there is to say.
            why = f"Due by {dueon:%m/%d/%Y}."
        out.append({**{k: rule[k] for k in ("code", "name", "authoritytype", "authority", "citation",
                                            "accountid", "qualificationcode", "authoritycategory",
                                            "enforcement", "legalreview", "program",
                                            "duestage", "duedays", "duetext", "blocking", "gate",
                                            "grouping",
                                            "note", "evidencekind",
                                            "evidencesource", "recurrence", "recurrencedays",
                                            "recurrencemonths")},
                    # A check that comes round on its own. The date still applies and still goes
                    # red when it lapses; it just does not belong on a screen of exceptions.
                    "scheduled": bool(rule.get("scheduled")),
                    "applies": reaches, "status": status, "why": why,
                    # Where the company has said another requirement's evidence answers this one
                    # (14-90.0041(1)(b): its own medical standard in place of FDOT's form), the two
                    # are one thing to keep on file, and the row folds into that one.
                    "foldinto": (rule["alternatesource"] if rule.get("alternatesource")
                                 and applies(condition(rule["alternatewhen"]), facts) is True
                                 else None),
                    # Which authority is behind this requirement for THIS driver, and the contract
                    # or policy named where it is the company's own. A screen that printed a
                    # federal citation beside a requirement the regulation does not impose would
                    # be telling an auditor the carrier cannot tell its obligations apart.
                    "because": because, "asking": asking,
                    "documentid": (evidence or {}).get("documentid"),
                    # Which record answered this, named so a reading can be recorded against the
                    # thing that was read rather than against the requirement in general.
                    "sourcetable": (evidence or {}).get("sourcetable"),
                    "sourceid": (evidence or {}).get("recordid"),
                    "on": (evidence or {}).get("effectiveon"),
                    # When it runs out, by the same arithmetic stand() uses to decide that it has.
                    # Without it on the item, a screen asking "what expires in the next 30 days"
                    # has to guess from the status word, which only says "soon".
                    "expireson": horizon(rule, evidence),
                    # When it falls due, for the stage that counts from the hire date rather than
                    # from the document.
                    "dueon": dueon})
    return _by_qualification(conn, _fold_alternates(_derive_file_rules(out)))


# When a thing falls due, earliest first.
STAGES = ("prehire", "predrive", "athire", "ongoing")

# Worst first. Where two rules are shown as one, the row says the worse of the two.
WORST_FIRST = ("failed", "expired", "overdue", "pending", "ordered", "review", "unknown",
               "expiring", "satisfied")


def contract_rules(conn: Connection, accountid: str) -> list[dict]:
    """What each reviewed, current broker contract asks of drivers, as rules.

    A contract requirement points at a catalog qualification. It reads the same evidence as the
    platform rule behind that qualification and carries the contract's own renewal, so it is one
    more source on the same row - never a second copy of the license or the screening. Where the
    contract requires its drivers to be approved, it reaches only approved drivers and the trips
    billed to it; otherwise every driver."""
    out = []
    for c in rows(conn, f"""
        SELECT r.recordid AS reqid, r.qualificationcode, r.renewaldays, r.clause,
               k.recordid AS contractid, k.broker, k.state, k.contractref, k.program,
               k.requiresapproval
        FROM contractrequirements r
        JOIN companycontracts k ON k.recordid = r.contractid AND k.accountid = r.accountid
        WHERE r.accountid = :a AND r.endedon IS NULL AND k.reviewed = 1 AND k.status = 'active'
          AND {payerlines.live("k")}
          AND (k.effectivefrom IS NULL OR k.effectivefrom <= CURDATE())
          AND (k.effectiveto IS NULL OR k.effectiveto >= CURDATE())
    """, a=accountid):
        base = row(conn, """
            SELECT * FROM compliancerules
            WHERE subject = 'driver' AND effectiveto IS NULL AND accountid IS NULL
              AND qualificationcode = :q AND evidencesource IS NOT NULL
            ORDER BY (authoritycategory = 'FEDERAL_GENERAL') DESC, sortorder LIMIT 1
        """, q=c["qualificationcode"])
        if not base:
            continue
        cid = c["contractid"]
        out.append({**base,
                    "code": f'CONTRACT:{c["reqid"]}', "name": base["name"],
                    "authoritytype": "contract", "authoritycategory": "CONTRACT_COMPANY",
                    "authority": " ".join(x for x in (c["broker"], c["state"]) if x),
                    "citation": " ".join(x for x in (c["contractref"], c["clause"]) if x) or None,
                    "applieswhen": None if not c["requiresapproval"] else json.dumps({"any": [
                        {"fact": "driver.contracts", "has": cid},
                        {"fact": "trip.contract", "eq": cid}]}),
                    "offered": 0, "extendable": 0, "program": c["program"],
                    "enforcement": "dispatch", "legalreview": "approved",
                    "recurrence": "days" if c["renewaldays"] else base["recurrence"],
                    "recurrencedays": c["renewaldays"] or base["recurrencedays"],
                    "grouping": "company"})
    return out


def _fold_alternates(out: list[dict]) -> list[dict]:
    """A rule the company has said is answered by another requirement's evidence joins that
    requirement's row, as one more source behind it. With the condition false, it stands alone."""
    owner = {i["evidencesource"]: i.get("qualificationcode") for i in out
             if i.get("evidencesource") and i.get("qualificationcode") and not i.get("foldinto")}
    for i in out:
        target = owner.get(i.get("foldinto"))
        if target:
            i["qualificationcode"], i["folded"] = target, True
    return out


def _by_qualification(conn: Connection, out: list[dict]) -> list[dict]:
    """One row per qualification, with every source behind it.

    Rules are the WHY and the catalog is the WHAT. Several rules may ask for the same qualification
    - the license under FMCSA and again under Medicaid, the pre-employment test under Part 382, the
    Florida intrastate statute and the CTD - and the driver's file shows the thing once. Each source
    is still evaluated on its own; the row takes the worse state among those that reach the driver,
    and lists them all, so nothing a stricter source asks is lost by being merged.

    The row keeps the code of its worst source, which is the one its dialog opens on. Sources that
    point at one qualification read the same evidence, so any of them opens the same record.

    An HR obligation never stops dispatch. It is still shown, chased and dated - it is simply not
    a reason to keep a driver off a trip."""
    names = {r["code"]: r["name"] for r in rows(conn, "SELECT code, name FROM qualificationcatalog")}
    rank = lambda o: (WORST_FIRST.index(o["status"])  # noqa: E731
                      if o["status"] in WORST_FIRST else len(WORST_FIRST))
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for item in out:
        if item.get("enforcement") == "hr":
            item["blocking"], item["gate"] = 0, "deficiency"
        key = item.get("qualificationcode") or f'rule:{item["code"]}'
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)
    merged = []
    for key in order:
        group = groups[key]
        reaching = [i for i in group if i["applies"] is True]
        pool = reaching or [i for i in group if i["applies"] is None] or group
        # Among equals, the requirement's own rule rather than one folded into it: it is the one
        # whose dialog shows the record the row is about.
        primary = dict(min(pool, key=lambda o: (rank(o), bool(o.get("folded")))))
        # A contract source may be the worst, but its dialog is the qualification's own rule.
        if primary["code"].startswith("CONTRACT:"):
            real = next((i for i in group if not i["code"].startswith("CONTRACT:")), None)
            if real:
                primary["code"] = real["code"]
        primary["sources"] = [{"code": i["code"], "authority": i["authority"],
                               "citation": i["citation"], "category": i.get("authoritycategory"),
                               "because": i.get("because"), "status": i["status"],
                               "legalreview": i.get("legalreview"), "program": i.get("program"),
                               "applies": i["applies"], "why": i.get("why")} for i in pool]
        if len(pool) > 1:
            primary["blocking"] = int(any(i.get("blocking") for i in pool))
            if any(i.get("gate") == "hardstop" for i in pool):
                primary["gate"] = "hardstop"
            stages = [i.get("duestage") or "prehire" for i in pool]
            primary["duestage"] = min(stages, key=lambda x: STAGES.index(x) if x in STAGES else 9)
        # General if any source behind it is general: the license counts toward every program,
        # even though one of its sources is Medicaid's.
        if any(i.get("program") is None for i in pool):
            primary["program"] = None
        if key in names:
            primary["name"] = names[key]
        merged.append(primary)
    return merged


def for_program(item: dict, program: str) -> dict | None:
    """The row as one program sees it: only the sources that are general or belong to that program,
    and the worse state among them. A merged row takes the worst of every source, which is right for
    the file and wrong for a badge - a shortfall only one program asks about must not count against
    another. None where nothing behind the row belongs to this program."""
    srcs = [s for s in (item.get("sources") or []) if s.get("program") in (None, program)]
    if not item.get("sources"):
        return item if item.get("program") in (None, program) else None
    if not srcs:
        return None
    rank = lambda s: (WORST_FIRST.index(s["status"])  # noqa: E731
                      if s["status"] in WORST_FIRST else len(WORST_FIRST))
    worst = min(srcs, key=rank)
    return {**item, "status": worst["status"], "why": worst.get("why") or item.get("why"),
            "applies": worst.get("applies", item["applies"]), "program": program}
