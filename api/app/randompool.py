###################################################################################################
# The random testing pool - 49 CFR 382.305.
#
# One definition of who is in it, because there were two and they disagreed. The rate denominator
# counted drivers whose operation was `cdl` or `cdlheavy`; the driver's own requirement read a
# date on the driver record. A CDL driver nobody had enrolled was in the pool for the arithmetic
# and out of it on their own file.
#
# Membership is a SPAN. One date with nothing to close it cannot answer the question a rate audit
# actually asks - who was in the pool on the day of that draw - because taking somebody out erases
# that they were ever in. A driver may also leave and come back, so there is one row per spell.
#
# THE AVERAGE, AND WHY IT IS NOT THE HEADCOUNT
#
# 382.305(b) sets the rate against "the average number of driver positions", not against the
# number on hand the day somebody looks. A carrier that runs twenty drivers all year and one that
# hires twenty in December owe very different numbers of tests, and the headcount cannot tell them
# apart. Spans can: average = member-days in the period / days in the period.
###################################################################################################
import math
from datetime import date

from sqlalchemy.engine import Connection

from app.db import newid, row, rows, run


def members_on(conn: Connection, accountid: str, on: date) -> int:
    """How many drivers were in the pool on one day. Inclusive of both ends of a spell."""
    return row(conn, """
        SELECT COUNT(*) AS n FROM randompoolmembership
        WHERE accountid = :a AND joinedon <= :on
          AND (leftpoolon IS NULL OR leftpoolon >= :on)
    """, a=accountid, on=on)["n"]


def members_now(conn: Connection, accountid: str) -> int:
    """How many drivers are in the pool as things stand - open spells only.

    Deliberately not members_on(today), and the difference is one day wide. A spell that ENDS
    today still covers today, so a draw made this morning was made against it and members_on is
    right to count it. But the driver has been taken out, cannot be drawn again, and a screen
    saying "1 in the pool" beside a list with nobody on it is the kind of small disagreement
    that turns into two pools.

    So: members_on answers "who was in the pool on that day", for draws and for the average.
    This answers "who is in it now", for the screen and for who may be drawn next.
    """
    return row(conn, """
        SELECT COUNT(*) AS n FROM randompoolmembership
        WHERE accountid = :a AND leftpoolon IS NULL
    """, a=accountid)["n"]


def spans(conn: Connection, accountid: str, start: date, end: date) -> list[dict]:
    """Every spell overlapping the period, clipped to it."""
    return rows(conn, """
        SELECT driverid, joinedon, leftpoolon FROM randompoolmembership
        WHERE accountid = :a AND joinedon <= :end
          AND (leftpoolon IS NULL OR leftpoolon >= :start)
    """, a=accountid, start=start, end=end)


def mean_of(held: list[dict], start: date, end: date) -> float:
    """The average number of driver positions across a period - 49 CFR 382.305(b).

    Member-days divided by days, both ends inclusive: a driver in the pool on the only day of a
    one-day period was in it for that day, not for none of it.

    Pure, and separated from the query on purpose. It is the denominator of every testing
    obligation the carrier has, an off-by-one here understates how many drivers must be tested,
    and arithmetic that decides that should be testable without a database."""
    if end < start:
        return 0.0
    days = (end - start).days + 1
    covered = 0
    for s in held:
        began = max(s["joinedon"], start)
        ended = min(s["leftpoolon"] or end, end)
        if ended >= began:
            covered += (ended - began).days + 1
    return covered / days


def average(conn: Connection, accountid: str, start: date, end: date) -> float:
    return mean_of(spans(conn, accountid, start, end), start, end)


def window(conn: Connection, accountid: str, year: int, upto: date) -> tuple[date, date]:
    """The period an average should be taken over, for this carrier, in this year.

    Not simply 1 January. A carrier that enrolled its first driver on 27 September has not had
    an average of 0.04 driver positions - it has had one driver for the time it has had a pool,
    and dividing twelve days by a whole year reports a pool of nothing while the rate quietly
    rounds back up to one. The number on screen has to be one somebody can recognise, or they
    stop believing the one beside it.

    So the period starts when the pool did, or at the turn of the year, whichever is later.
    """
    began = row(conn, "SELECT MIN(joinedon) AS first FROM randompoolmembership "
                      "WHERE accountid = :a", a=accountid)
    first = (began or {}).get("first")
    start = date(year, 1, 1)
    if first and first > start:
        start = first
    # NOT max(upto, start). A pool that began in September 2026 did not exist in 2025, and
    # forcing the end past the start to avoid an empty range made the 2025 figure read "1
    # average driver position, counted from 09/27/2026" - a date in the wrong year, against a
    # year nobody was covered in. An empty range is the right answer and mean_of returns 0 for
    # it.
    return start, min(upto, date(year, 12, 31))


def owed(pool: float, rate: int) -> int:
    """How many tests a rate asks of a pool that size - 49 CFR 382.305(b).

    Rounded UP. A rate of 50% against an average of 1.4 positions is 0.7 tests, and a carrier
    that rounds its obligation down to zero has tested nobody all year while reporting that it
    met the rate. An empty pool owes nothing, which is the one case that is genuinely zero."""
    if pool <= 0:
        return 0
    return math.ceil(pool * rate / 100)


def standing(conn: Connection, accountid: str, driverid: str) -> dict | None:
    """This driver's current spell, or the last one they had. None if never enrolled."""
    return row(conn, """
        SELECT recordid, joinedon, leftpoolon, reason FROM randompoolmembership
        WHERE accountid = :a AND driverid = :d
        ORDER BY joinedon DESC, added DESC LIMIT 1
    """, a=accountid, d=driverid)


def is_member(conn: Connection, accountid: str, driverid: str, on: date | None = None) -> bool:
    held = standing(conn, accountid, driverid)
    on = on or date.today()
    return bool(held and held["joinedon"] <= on
                and (held["leftpoolon"] is None or held["leftpoolon"] >= on))


def join(conn: Connection, accountid: str, driverid: str, on: date,
         reason: str | None = None, by: str | None = None) -> str | None:
    """Put a driver in the pool. Does nothing if they are already in it - a second open spell
    would double-count them in every average from then on."""
    if is_member(conn, accountid, driverid, on):
        return None
    rid = newid()
    run(conn, """
        INSERT INTO randompoolmembership (recordid, accountid, driverid, joinedon, reason, addedby)
        VALUES (:id, :a, :d, :on, :r, :u)
    """, id=rid, a=accountid, d=driverid, on=on, r=reason, u=by)
    return rid


def leave(conn: Connection, accountid: str, driverid: str, on: date,
          reason: str | None = None) -> bool:
    """Close the open spell. The spell stays on the record - that is the whole point of it."""
    held = row(conn, """
        SELECT recordid, joinedon FROM randompoolmembership
        WHERE accountid = :a AND driverid = :d AND leftpoolon IS NULL
        ORDER BY joinedon DESC LIMIT 1
    """, a=accountid, d=driverid)
    if not held:
        return False
    # A spell cannot end before it began; somebody taken out on the day they went in was in the
    # pool for that day.
    ends = max(on, held["joinedon"])
    run(conn, """
        UPDATE randompoolmembership SET leftpoolon = :on, reason = COALESCE(:r, reason)
        WHERE recordid = :id
    """, id=held["recordid"], on=ends, r=reason)
    return True


# ------------------------------------------------------------------------------------------------
# Who came out of a draw, and what happened to them.
# ------------------------------------------------------------------------------------------------

def select(conn: Connection, accountid: str, selectionid: str, driverids: list[str],
           by: str | None = None) -> int:
    """Name the drivers a draw produced. Returns how many were written.

    The count on the draw is these rows, not a number somebody typed beside them - the same
    treatment the pool size got, and for the same reason."""
    written = 0
    for driverid in dict.fromkeys(driverids):
        if row(conn, "SELECT recordid FROM randomselecteddrivers "
                     "WHERE selectionid = :s AND driverid = :d", s=selectionid, d=driverid):
            continue
        run(conn, """
            INSERT INTO randomselecteddrivers (recordid, accountid, selectionid, driverid, addedby)
            VALUES (:id, :a, :s, :d, :u)
        """, id=newid(), a=accountid, s=selectionid, d=driverid, u=by)
        written += 1
    return written


def chosen(conn: Connection, accountid: str, selectionid: str) -> list[dict]:
    """Everyone a draw named, and where each of them got to."""
    return rows(conn, """
        SELECT x.recordid, x.driverid, x.notifiedon, x.testid, x.excused, x.excusedon,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS driver,
               t.collectedon, t.result
        FROM randomselecteddrivers x
        JOIN drivers d ON d.recordid = x.driverid
        LEFT JOIN drugtests t ON t.recordid = x.testid AND t.withdrawn IS NULL
        WHERE x.accountid = :a AND x.selectionid = :s
        ORDER BY d.lastname, d.firstname
    """, a=accountid, s=selectionid)


def owing(conn: Connection, accountid: str, driverid: str) -> dict | None:
    """The oldest selection on this driver that has neither a test nor a recorded reason."""
    return row(conn, """
        SELECT x.recordid, x.selectionid, x.notifiedon, s.drawnon, s.testtype
        FROM randomselecteddrivers x
        JOIN randomselections s ON s.recordid = x.selectionid AND s.deleted IS NULL
        WHERE x.accountid = :a AND x.driverid = :d
          AND x.testid IS NULL AND x.excusedon IS NULL
        ORDER BY s.drawnon ASC, x.added ASC LIMIT 1
    """, a=accountid, d=driverid)


def answer(conn: Connection, accountid: str, driverid: str, testid: str) -> bool:
    """Link a random test to the selection it answers.

    Called when the test is filed rather than asked for as a separate step: a driver has at most
    one selection outstanding in practice, and making somebody tie the two together by hand is
    how the link would come to be missing on exactly the files where it matters."""
    open_one = owing(conn, accountid, driverid)
    if not open_one:
        return False
    run(conn, "UPDATE randomselecteddrivers SET testid = :t WHERE recordid = :id",
        t=testid, id=open_one["recordid"])
    return True


def excuse(conn: Connection, accountid: str, recordid: str, reason: str, on: date) -> None:
    run(conn, """
        UPDATE randomselecteddrivers SET excused = :r, excusedon = :on
        WHERE recordid = :id AND accountid = :a
    """, id=recordid, a=accountid, r=reason[:255], on=on)


# ------------------------------------------------------------------------------------------------
# Leaving the pool
#
# The pool is the drivers who PERFORM SAFETY-SENSITIVE FUNCTIONS and are reached by Part 382. A
# driver leaves it by ceasing to be one of those, and nothing else - not by going on holiday, and
# not by having just been tested. A driver who is away the week their name comes out stays in the
# pool and the draw records why they were not tested; random that exempts whoever was busy is not
# random.
#
# Said in ONE place and called from everywhere that can change the answer, because four copies of
# "is this person still in the pool" is four chances to disagree - which is the fault that put two
# different pools in this product to begin with.
#
# The worst of these is the prohibition. 382.501 removes a driver from safety-sensitive functions,
# so they are not in the random pool at all: they are in the return-to-duty process and then in
# follow-up testing, which is its own schedule under 40.307. Leaving them in meant the software
# could select a prohibited driver for a random test they must not take - causing a compliance
# error rather than merely failing to catch one.
# ------------------------------------------------------------------------------------------------

def why_out(conn: Connection, accountid: str, driverid: str) -> str | None:
    """Why this driver no longer belongs in the pool, in the words that go on the record.
    None means they still belong in it."""
    from app import eligibility                    # late: eligibility files tests through here
    from app.facts import CDL_OPERATIONS           # late: facts reads this module

    held = row(conn, """
        SELECT status, terminatedon, operation, deleted FROM drivers
        WHERE recordid = :d AND accountid = :a
    """, a=accountid, d=driverid)
    if not held or held["deleted"]:
        return "No longer on the roster"
    if held["terminatedon"]:
        return f'Terminated {held["terminatedon"]:%m/%d/%Y}'
    if held["status"] in ("inactive", "declined"):
        return "Taken off the roster"
    if (held["operation"] or "noncmv") not in CDL_OPERATIONS:
        return "No longer operating a vehicle that requires a CDL"
    bar = eligibility.standing(conn, accountid, driverid)
    if bar:
        return (f'Prohibited from safety-sensitive functions {bar["startedon"]:%m/%d/%Y}'
                if bar.get("startedon") else "Prohibited from safety-sensitive functions")
    return None


def reconcile(conn: Connection, accountid: str, driverid: str,
              on: date | None = None) -> str | None:
    """Close the spell if the driver no longer belongs in the pool. Returns why, or None.

    Only ever takes somebody OUT. Putting a driver back after a return to duty is a decision
    about placing them on safety-sensitive work again, and the software does not make that one
    quietly - their own file says the pool membership is owed instead.
    """
    why = why_out(conn, accountid, driverid)
    if why and leave(conn, accountid, driverid, on or date.today(), why):
        return why
    return None


def test_owed(conn: Connection, accountid: str, driverid: str) -> bool:
    """Whether this driver owes a test from a selection. The fact behind RANDOM_TEST_OWED."""
    return bool(owing(conn, accountid, driverid))


__all__ = ["members_on", "members_now", "spans", "average", "mean_of", "window", "owed",
           "select", "chosen", "owing", "answer", "excuse", "test_owed",
           "why_out", "reconcile", "standing", "is_member", "join", "leave"]
