###################################################################################################
# Whether a driver may drive today - which is a different question from whether their file is in
# order.
#
# 49 CFR 382.501: after a positive test or a refusal, an employer must not let the driver perform
# any safety-sensitive function until the return-to-duty process has been completed. The same bar
# follows from a Clearinghouse query that comes back prohibited (382.701) and from actual knowledge
# of a violation (382.107), neither of which involves a test result in this office's hands.
#
# Three things this module is careful about, because each is a way of getting it wrong:
#
#   A cancelled test is not a test (40.23(f)). It satisfies nothing and prohibits nobody; what it
#   creates is the need for another collection.
#
#   A refusal is a positive. So are adulterated and substituted results (40.191). They all produce
#   the same bar, and pretending otherwise would let a refusal through.
#
#   Part 382 reaches commercial drivers. A positive on a company's own screen for a driver who is
#   not operating commercial vehicles is an employment matter for that company - it is not a
#   federal prohibition, and this will not say it is.
#
# Clearing the bar is the return-to-duty process and nothing less: a SAP evaluation, whatever
# education or treatment the SAP prescribed, the SAP's follow-up determination, and a negative
# return-to-duty test (40.305). Afterwards the SAP's follow-up testing plan runs on (40.307,
# 382.311) - that is an obligation, not a bar, and is tracked rather than enforced here.
###################################################################################################
from datetime import date

from sqlalchemy.engine import Connection

from app.db import newid, row, rows, run, utcnow

# What a test came back as, in the words the lab uses.
RESULTS = {
    "negative": "Negative",
    "negativedilute": "Negative - dilute",
    "positive": "Positive",
    "refusal": "Refusal to test",
    "adulterated": "Adulterated",
    "substituted": "Substituted",
    "cancelled": "Cancelled",
    "pending": "Pending",
}

# The results that bar a driver from safety-sensitive work. A refusal is a violation in its own
# right (382.211), and an adulterated or substituted specimen is a refusal (40.191).
PROHIBITING = ("positive", "refusal", "adulterated", "substituted")
# The results that answer the pre-employment requirement. A dilute negative is still a negative;
# whether to recollect is the company's policy question (40.197), not a bar.
SATISFYING = ("negative", "negativedilute")

REASONS = {
    "preemployment": "Pre-employment",
    "random": "Random",
    "postaccident": "Post-accident",
    "reasonablesuspicion": "Reasonable suspicion",
    "returntoduty": "Return-to-duty",
    "followup": "Follow-up",
}

# The employment decision after a violation - the employer's, not DOT's. Offered as two answers
# because there are two, and neither is what the regulation requires: 49 CFR Part 40 and Part 382
# decide what the person may DO, and say nothing about whether they are employed.
DECISIONS = {
    "donothire": "Not hired",
    "continue": "Kept on through the return-to-duty process",
}

SOURCES = {
    "test": "A DOT test came back {result}",
    "clearinghouse": "The FMCSA Clearinghouse shows this driver prohibited",
    "actualknowledge": "The employer has actual knowledge of a drug or alcohol violation",
}


# Which drug and alcohol program a driver is under. They are not variations of one another: each
# has its own authority, its own consequences for a positive, and its own way back.
PROGRAMMES = {
    "dot": "DOT - 49 CFR Part 382",
    "ctd": "Florida CTD - F.A.C. 41-2.006(4)(a)",
    "broker": "Broker or contractual",
    "company": "Company (non-DOT)",
}

# What clearing a bar is called under each, and what it actually requires. The DOT process is the
# only one that may be called a SAP process: a DOT SAP is a defined qualification (49 CFR 40.281),
# and describing a company's own evaluation that way would be a false statement in a record an
# auditor reads.
RETURN_TO_DUTY = {
    "dot": "A DOT-qualified substance abuse professional must evaluate the driver, the driver must "
           "complete what the SAP prescribes, and a return-to-duty test must come back negative "
           "(49 CFR 40.305).",
    "ctd": "The driver must be removed from safety-sensitive duty and may return only once the "
           "evaluation and return-to-duty requirements of the CTD program are met.",
    "broker": "Whatever the contract requires before the driver may carry its trips again.",
    "company": "Whatever the company's own policy requires. This is an employment matter, not a "
               "federal or state prohibition.",
}


def covered(driver: dict) -> bool:
    """Whether Part 382 reaches this driver at all. The company's own answer settles it; failing
    that, a commercial license class does."""
    if driver.get("operatescmv") is not None:
        return bool(driver["operatescmv"])
    return (driver.get("licenseclass") or "").upper() in ("A", "B", "C")


def program(driver: dict, transit: bool | None = None) -> str | None:
    """Which program governs this driver's testing, or None if nothing does.

    Said outright where somebody has said it. Otherwise Part 382 if it reaches them - the federal
    program is not optional where it applies - and failing that the Florida CTD program where
    the company works under a CTC or TD contract. A driver under none of them can still be tested
    by their employer; what they cannot be is federally prohibited."""
    said = (driver.get("datprogram") or "").strip().lower()
    if said in PROGRAMMES:
        return said
    if covered(driver):
        return "dot"
    if transit:
        return "ctd"
    return None


# Where a driver stands on drug and alcohol, as a status rather than as the last test result.
#
# Reading `last test = positive` is the trap: a driver can be prohibited by a refusal, by an
# adulterated or substituted specimen, by an alcohol result of 0.04 or more, by the Clearinghouse,
# or by the employer's actual knowledge - none of which is a positive test - and a driver who IS
# prohibited may well have a negative return-to-duty test as their most recent one. The status is
# the fact; the tests are how it got there.
DA_STATUS = {
    "qualified": "Qualified",
    "prohibited": "Prohibited",
    "rtdinprogress": "Return-to-duty process in progress",
    "notapplicable": "Not applicable",
}


def da_status(conn: Connection, accountid: str, driverid: str, driver: dict,
              transit: bool | None = None) -> dict:
    """QUALIFIED | PROHIBITED | RTD IN PROGRESS | NOT APPLICABLE, and why.

    "Return-to-duty in progress" is not a softer kind of prohibited - the driver may not perform
    safety-sensitive functions in either state. It is reported separately because the two need
    different things from the office: one needs a decision, the other needs chasing."""
    under = program(driver, transit)
    if not under:
        return {"status": "notapplicable", "program": None,
                "why": "No drug and alcohol program reaches this driver."}
    held = standing(conn, accountid, driverid)
    if not held:
        return {"status": "qualified", "program": under,
                "why": "No drug or alcohol violation on file."}
    # Started down the road back: a SAP named, or an evaluation done. Still prohibited either way.
    started = bool(held.get("sapname") or held.get("sapevaluatedon") or held.get("sapcompliedon")
                   or held.get("decision") == "continue")
    return {"status": "rtdinprogress" if started else "prohibited", "program": under,
            "why": held["reason"], "since": held["startedon"], "prohibition": held["recordid"]}


# The Clearinghouse answers two questions and they are not the same question. A query that is
# current and says "not prohibited" is one state; a driver nobody has queried this year is another;
# and a driver the Clearinghouse says is prohibited is a third. Running them together loses the
# difference between "we have not asked" and "the answer was no".
QUERY_STATUS = {"current": "Current", "overdue": "Overdue", "pending": "Pending",
                "notapplicable": "Not applicable"}
DRIVER_STATUS = {"notprohibited": "Not prohibited", "prohibited": "Prohibited",
                 "unknown": "Not known"}


def clearinghouse(conn: Connection, accountid: str, driverid: str, driver: dict,
                  today: date | None = None) -> dict:
    """The query, and the driver - separately.

    The Clearinghouse reaches drivers subject to the CDL requirements and Part 382, not every NEMT
    driver, so "not applicable" is a real answer and not a gap."""
    today = today or date.today()
    if not covered(driver):
        return {"query": "notapplicable", "driver": "unknown",
                "why": "The Clearinghouse does not reach this driver."}
    got = rows(conn, """
        SELECT issuedon, receivedon, outcome, reviewstate
        FROM driverreports
        WHERE accountid = :a AND driverid = :d AND code LIKE 'CLEARINGHOUSE%'
        ORDER BY COALESCE(issuedon, DATE(orderedon)) DESC, createdon DESC
    """, a=accountid, d=driverid)
    answered = [q for q in got if q["outcome"]]
    waiting = [q for q in got if not q["receivedon"] or q["reviewstate"] != "reviewed"]
    latest = answered[0] if answered else None

    if latest and latest["issuedon"]:
        # 382.701(b): at least once every twelve months.
        query = "current" if (today - latest["issuedon"]).days <= 365 else "overdue"
    elif waiting:
        query = "pending"
    else:
        query = "overdue"
    return {"query": query,
            "driver": ("prohibited" if latest and latest["outcome"] == "prohibited"
                       else "notprohibited" if latest else "unknown"),
            "queriedon": latest["issuedon"] if latest else None,
            "why": None}


def standing(conn: Connection, accountid: str, driverid: str) -> dict | None:
    """The prohibition in force, if there is one. Nothing here asks whether the driver is covered -
    that is the caller's question, because the same record means different things for a driver
    Part 382 reaches and one it does not."""
    return row(conn, """
        SELECT recordid, source, program, reason, startedon, sapname, sapevaluatedon, sapcompliedon,
               sapinfogivenon, sapinfogivenby, sapinfodocumentid, decision, decidedon, rtdtestid,
               followuptests, followupuntil, documentid, note, testid
        FROM driverprohibitions
        WHERE accountid = :a AND driverid = :d AND clearedon IS NULL AND withdrawn IS NULL
        ORDER BY startedon DESC, createdon DESC LIMIT 1
    """, a=accountid, d=driverid)


def prohibit(conn: Connection, accountid: str, driverid: str, *, source: str, reason: str,
             startedon: date, testid: str | None = None, note: str | None = None,
             enteredby: str | None = None, program: str | None = None) -> str | None:
    """Record a bar on safety-sensitive work. One at a time: a second violation while the first is
    unresolved does not need a second row to say the same thing."""
    held = standing(conn, accountid, driverid)
    if held:
        return None
    pid = newid()
    run(conn, """
        INSERT INTO driverprohibitions (recordid, accountid, driverid, source, program, reason,
                                        testid, startedon, note, enteredby)
        VALUES (:id, :a, :d, :s, :p, :r, :t, :on, :n, :u)
    """, id=pid, a=accountid, d=driverid, s=source, p=program, r=reason[:255], t=testid,
        on=startedon, n=(note or None), u=enteredby)

    # 382.501 removes this driver from safety-sensitive functions, so they are out of the random
    # pool from today: not on hold in it, out of it. What they owe now is the return-to-duty
    # process and then follow-up testing under 40.307, which is its own schedule. Left in, the
    # software could select a prohibited driver for a random test they must not take.
    from app import randompool
    randompool.reconcile(conn, accountid, driverid, on=startedon)

    return pid


def file_test(conn: Connection, accountid: str, driverid: str, driver: dict, *, reason: str,
              collectedon: date, result: str, documentid: str | None = None,
              note: str | None = None, enteredby: str | None = None,
              transit: bool | None = None, testtype: str | None = None,
              substance: str | None = None, bac: float | None = None) -> dict:
    """File one test, and let it do what its result does.

    A prohibiting result bars a covered driver from safety-sensitive work from the day of the
    collection. A negative return-to-duty test is the last step of clearing that bar, so it lifts
    it. Everything else is simply recorded."""
    if result not in RESULTS:
        raise ValueError("Unknown result")
    if reason not in REASONS:
        raise ValueError("Unknown reason for testing")
    testid = newid()
    run(conn, """
        INSERT INTO drugtests (recordid, accountid, driverid, reason, collectedon, result,
                               testtype, substance, bac, documentid, note, enteredby)
        VALUES (:id, :a, :d, :why, :on, :r, :tt, :sub, :bac, :doc, :n, :u)
    """, id=testid, a=accountid, d=driverid, why=reason, on=collectedon, r=result,
        tt=(testtype if testtype in ("drug", "alcohol") else None),
        sub=(substance or None), bac=bac, doc=documentid,
        n=(note or None), u=enteredby)

    # A random test answers the selection that called for it. Linked here rather than asked for
    # as a separate step: a driver has at most one selection outstanding in practice, and making
    # somebody tie the two together by hand is how the link comes to be missing on exactly the
    # files where somebody later needs it.
    if reason == "random":
        from app import randompool
        randompool.answer(conn, accountid, driverid, testid)

    out = {"recordid": testid, "prohibited": None, "cleared": None, "program": None}
    under = program(driver, transit)
    if result in PROHIBITING and under:
        # The bar follows whichever program reaches the driver, and says which one. Reading only
        # for a federal hook left a CTD driver with a positive on file and nothing stopping them.
        out["program"] = under
        said = "A DOT test" if under == "dot" else "A test"
        out["prohibited"] = prohibit(
            conn, accountid, driverid, source="test", program=under,
            reason=f'{said} came back {RESULTS[result].lower()}' +
                   f' ({REASONS[reason].lower()}, {collectedon:%m/%d/%Y})',
            startedon=collectedon, testid=testid, enteredby=enteredby)
    elif result in SATISFYING and reason == "returntoduty":
        held = standing(conn, accountid, driverid)
        # The test is the last step, not the whole process: it only lifts the bar where the SAP has
        # evaluated the driver and found they complied with what was prescribed (40.305).
        # Only the DOT process turns on a SAP determination. Under the others, the return-to-duty
        # test is the step that closes it out - there is no DOT SAP in them to wait for.
        if held and (held["sapcompliedon"] or (held.get("program") or "dot") != "dot"):
            run(conn, """
                UPDATE driverprohibitions SET rtdtestid = :t, clearedon = :on, clearedby = :u
                WHERE recordid = :id
            """, t=testid, on=collectedon, u=enteredby, id=held["recordid"])
            out["cleared"] = held["recordid"]
    return {**out, "result": result}


def withdraw(conn: Connection, accountid: str, driverid: str, testid: str, *,
             reason: str, by: str | None = None) -> dict:
    """Take back a test that was filed on the wrong driver, and undo what it did.

    A drug test is never just a row. Filing one can raise a bar on safety-sensitive work, lift
    one, answer a random selection, or close out a post-accident obligation - so taking it back
    has to reverse each of those, and a correction that reverses three of the four leaves the
    file saying something that was never true.

    WITHDRAWN, NOT DELETED. 49 CFR 382.401 asks the carrier to keep these records, and a
    positive result that simply disappears out of a file is the worst thing an auditor can find:
    a withdrawn row with a date, a person and a reason is a correction anybody can follow, while
    a missing row is indistinguishable from a cover-up.

    Returns what was undone, so the office can be told rather than left to guess.
    """
    held = row(conn, """
        SELECT recordid, reason, result, collectedon FROM drugtests
        WHERE recordid = :t AND accountid = :a AND driverid = :d AND withdrawn IS NULL
    """, t=testid, a=accountid, d=driverid)
    if not held:
        raise ValueError("No such test on this driver")
    undone = []

    # 1. A bar this test raised comes down. It was raised by something that did not happen to
    #    this person, so it is withdrawn the same visible way rather than marked "cleared" -
    #    cleared would say they completed the return-to-duty process, which they did not.
    for bar in rows(conn, """
        SELECT recordid, reason FROM driverprohibitions
        WHERE accountid = :a AND driverid = :d AND testid = :t AND withdrawn IS NULL
    """, a=accountid, d=driverid, t=testid):
        run(conn, """
            UPDATE driverprohibitions
               SET withdrawn = :now, withdrawnby = :u, withdrawnreason = :r
             WHERE recordid = :id
        """, id=bar["recordid"], now=utcnow(), u=by, r=reason[:255])
        undone.append("The bar on safety-sensitive work this test raised has been lifted")

    # 2. A bar this test LIFTED goes back up. This is the dangerous direction: a return-to-duty
    #    test filed on the wrong driver cleared a prohibition that should still be standing, and
    #    forgetting this leaves somebody driving who may not.
    for bar in rows(conn, """
        SELECT recordid FROM driverprohibitions
        WHERE accountid = :a AND driverid = :d AND rtdtestid = :t AND withdrawn IS NULL
    """, a=accountid, d=driverid, t=testid):
        run(conn, """
            UPDATE driverprohibitions SET rtdtestid = NULL, clearedon = NULL, clearedby = NULL
            WHERE recordid = :id
        """, id=bar["recordid"])
        undone.append("The bar this test lifted is back in force - the driver may not perform "
                      "safety-sensitive functions")

    # 3. A random selection it answered is owed again.
    n = run(conn, """
        UPDATE randomselecteddrivers SET testid = NULL
        WHERE accountid = :a AND driverid = :d AND testid = :t
    """, a=accountid, d=driverid, t=testid).rowcount
    if n:
        undone.append("The random selection this test answered is owed again")

    # 4. And a post-accident obligation it closed out.
    for which in ("alcoholtestid", "drugtestid"):
        n = run(conn, f"""
            UPDATE driveraccidents SET {which} = NULL
            WHERE accountid = :a AND driverid = :d AND {which} = :t
        """, a=accountid, d=driverid, t=testid).rowcount
        if n:
            undone.append("The post-accident test this answered is owed again")

    run(conn, """
        UPDATE drugtests SET withdrawn = :now, withdrawnby = :u, withdrawnreason = :r
        WHERE recordid = :t AND accountid = :a
    """, t=testid, a=accountid, now=utcnow(), u=by, r=reason[:255])
    return {"test": held, "undone": undone}


def owed(held: dict | None) -> list[dict]:
    """What is still owed on a bar in force, as plain sentences.

    Two of these are obligations rather than steps on the way back: the SAP information is owed to
    the applicant whatever the company decides about hiring them (49 CFR 40.287), and the hiring
    decision is owed to nobody but is unmade until somebody makes it. Keeping them in one list is
    what stops "we are not hiring him" from quietly closing the file with the duty unperformed."""
    if not held:
        return []
    out = []
    if not held.get("sapinfogivenon"):
        out.append({"what": "sapinfo",
                    "says": "Give the applicant a list of DOT-qualified substance abuse "
                            "professionals. This is owed under 49 CFR 40.287 whether or not they "
                            "are hired."})
    if not held.get("decision"):
        out.append({"what": "decision",
                    "says": "Decide whether to keep this applicant. DOT does not decide it - the "
                            "bar on safety-sensitive work stands either way."})
    elif held["decision"] == "continue" and not held.get("sapcompliedon"):
        out.append({"what": "rtd",
                    "says": "The return-to-duty process: a SAP evaluation, whatever the SAP "
                            "prescribes, and a negative return-to-duty test (49 CFR 40.305)."})
    # The last step, and the one this list used to stop short of.
    #
    # The old test ran "has the SAP said they complied - if so there is nothing outstanding", which
    # is the whole process except its ending. 49 CFR 40.305 is explicit that the driver may not
    # resume safety-sensitive functions until a return-to-duty test has been conducted and the
    # result is negative. So a file could show the SAP named, the evaluation done, compliance
    # recorded and the decision made, report nothing owed, and still hold a driver who may not
    # drive - which is precisely the state somebody reads this list to avoid being in.
    elif held["decision"] == "continue" and not held.get("rtdtestid"):
        out.append({"what": "rtdtest",
                    "says": "A return-to-duty test with a negative result. The SAP has recorded "
                            "that this driver complied with what was prescribed; until the test is "
                            "on file they may not perform safety-sensitive functions "
                            "(49 CFR 40.305)."})
    return out


def tests(conn: Connection, accountid: str, driverid: str) -> list[dict]:
    """Every test on file for this driver, newest first."""
    return rows(conn, """
        SELECT t.recordid, t.reason, t.collectedon, t.result, t.documentid, t.note, t.createdon,
               d.filename
        FROM drugtests t LEFT JOIN documents d ON d.recordid = t.documentid AND d.deleted IS NULL
        WHERE t.accountid = :a AND t.driverid = :d AND t.withdrawn IS NULL
        ORDER BY t.collectedon DESC, t.createdon DESC
    """, a=accountid, d=driverid)


def history(conn: Connection, accountid: str, driverid: str) -> list[dict]:
    """Every prohibition, standing or lifted.

    Carries the documents and the test that caused it, because a LIFTED prohibition is still the
    answer to a question somebody asks: a positive from last March opens on screen showing the
    day it was collected and nothing else, when what the reader wants is what it led to - the
    SAP who evaluated the driver, the determination, the list of professionals handed over, and
    the day the bar came off."""
    return rows(conn, """
        SELECT recordid, source, program, reason, startedon, sapname, sapevaluatedon,
               sapcompliedon, sapinfogivenon, decision, decidedon, clearedon, followuptests,
               followupuntil, note, testid, rtdtestid, documentid, sapinfodocumentid
        FROM driverprohibitions WHERE accountid = :a AND driverid = :d AND withdrawn IS NULL
        ORDER BY startedon DESC, createdon DESC
    """, a=accountid, d=driverid)


def preemployment_state(conn: Connection, accountid: str, driverid: str) -> dict:
    """Where the pre-employment requirement stands.

    49 CFR 382.301(a): no safety-sensitive function until the employer has a negative controlled
    substances result for this driver. A negative return-to-duty test is such a result - it is what
    permits the driver to work again (40.305), so a driver who failed pre-employment and completed
    the return-to-duty process is not sent back for another pre-employment collection.

    A cancelled test answers nothing (40.23(f)), so a driver whose only test was cancelled stands
    exactly where an untested one does."""
    held = tests(conn, accountid, driverid)
    # A bar in force answers the question by itself: nothing is satisfied while the driver may not
    # perform the work.
    barred = standing(conn, accountid, driverid)
    if barred:
        return {"state": "blocked", "on": str(barred["startedon"]), "why": barred["reason"]}
    clearing = [t for t in held if t["reason"] in ("preemployment", "returntoduty")
                and t["result"] in SATISFYING]
    if clearing:
        # Say which test answered it - a return-to-duty negative is not a pre-employment test, and
        # the file should not pretend it was one.
        return {"state": "received", "on": str(clearing[0]["collectedon"]), "why": None,
                "how": f'Negative {REASONS[clearing[0]["reason"]].lower()} test'}
    mine = [t for t in held if t["reason"] == "preemployment"]
    if not mine:
        return {"state": "todo", "on": None, "why": None}
    if mine[0]["result"] == "cancelled":
        return {"state": "todo", "on": None,
                "why": "The pre-employment test was cancelled - a cancelled test is not a test, "
                       "so another collection is owed"}
    return {"state": "todo", "on": None, "why": "The pre-employment test result is still pending"}
