###################################################################################################
# The road test - 49 CFR 391.31 - as one event with one output.
#
# The regulation says what must be examined, and it is not a driving test somebody invented: the
# areas in ITEMS are 391.31(c)'s own list. The examiner rates each one and then forms a view. There
# is deliberately NO SCORE: 391.31 does not say that 82% is a pass, it says the examiner decides
# whether the driver can operate the vehicle safely. A number would invent a threshold the
# regulation does not have and would make a bad result look arguable.
#
# N/A is a real answer. Coupling a trailer has nothing to do with a wheelchair bus, and an examiner
# forced to rate it would either lie or leave the form unfinished.
#
# WHAT IS FEDERAL AND WHAT IS OURS
#
# The passenger items - securement, the lift, assisting somebody into a seat - are not 391.31.
# They matter enormously for NEMT and they are a company, state or broker requirement, so they are
# kept in their own section and their own column. Running them together would let a file claim
# federal authority for a company's own checklist.
###################################################################################################
import json
import secrets
from datetime import date, timedelta

from sqlalchemy.engine import Connection

from app.config import settings
from app.db import newid, row, rows, run, utcnow

# How long an examiner's link lives. Shorter than an employer's: the test is a booked event, not a
# letter somebody may answer in a month.
VALID_DAYS = 21

# 49 CFR 391.31(c) - the areas the regulation itself lists.
ITEMS = (
    ("pretrip", "Pre-trip inspection"),
    ("controls", "Vehicle controls and equipment"),
    ("starting", "Starting and placing the vehicle in operation"),
    ("transmission", "Use of transmission and gears"),
    ("turning", "Turning"),
    ("braking", "Braking and stopping"),
    ("traffic", "Operating in traffic"),
    ("passing", "Passing other vehicles"),
    ("mirrors", "Use of mirrors and signals"),
    ("speed", "Speed and space management"),
    ("railroad", "Railroad crossings"),
    ("grades", "Grades and hills"),
    ("backing", "Backing"),
    ("parking", "Parking"),
    ("coupling", "Coupling and uncoupling"),
)

# The passenger work. Ours, not the FMCSA's - see the note at the top.
EXTRAS = (
    ("loading", "Safe passenger loading and unloading"),
    ("curb", "Curb approach and departure"),
    ("doors", "Door operation"),
    ("lift", "Lift or ramp operation"),
    ("securement", "Wheelchair securement"),
    ("restraints", "Occupant restraints"),
    ("mobility", "Handling mobility devices"),
    ("assistance", "Passenger assistance"),
    ("emergency", "Emergency equipment and procedures"),
)

RATINGS = {"s": "Satisfactory", "ni": "Needs improvement", "u": "Unsatisfactory", "na": "N/A"}
RESULTS = {"pass": "Pass", "fail": "Fail"}
VEHICLE_TYPES = {"car": "Passenger car or van", "cmv": "Passenger commercial motor vehicle",
                 "bus": "Bus", "other": "Other commercial motor vehicle"}


def link_for(token: str) -> str:
    return f"{settings.public_url.rstrip('/')}/road-test/{token}"


def create(conn: Connection, accountid: str, driverid: str, createdby: str | None = None) -> str:
    """Open a road test for an examiner to administer."""
    rid = newid()
    run(conn, """
        INSERT INTO roadtests (recordid, accountid, driverid, token, expireson, createdby)
        VALUES (:id, :a, :d, :tok, :exp, :u)
    """, id=rid, a=accountid, d=driverid, tok=secrets.token_urlsafe(32),
        exp=utcnow() + timedelta(days=VALID_DAYS), u=createdby)
    return rid


def standing(test: dict) -> tuple[str, str]:
    """Where one road test stands, and the sentence for it."""
    if test.get("completedon") and not test.get("reviewedon"):
        return "toreview", (f'{RESULTS.get(test.get("result"), "Completed")} '
                            f'{test["completedon"]:%m/%d/%Y}, unread')
    if test.get("completedon"):
        return ("passed" if test.get("result") == "pass" else "failed",
                f'{RESULTS.get(test.get("result"), "Completed")} {test["completedon"]:%m/%d/%Y}')
    if test.get("senton"):
        return "waiting", f'Sent to the examiner {test["senton"]:%m/%d/%Y}, not back yet'
    return "open", "Not sent to an examiner yet"


def _parsed(value):
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return value or {}


def for_driver(conn: Connection, accountid: str, driverid: str) -> list[dict]:
    """Every road test on this driver, newest first, each with where it stands."""
    out = []
    for t in rows(conn, """
        SELECT * FROM roadtests WHERE accountid = :a AND driverid = :d
        ORDER BY COALESCE(testedon, DATE(createdon)) DESC, createdon DESC
    """, a=accountid, d=driverid):
        got = dict(t)
        # MariaDB hands JSON back as a string through PyMySQL, so it is parsed here rather than
        # left for every reader to discover that `ratings` is text that looks like a map.
        got["ratings"] = _parsed(got.get("ratings"))
        got["extras"] = _parsed(got.get("extras"))
        state, says = standing(got)
        out.append({**got, "state": state, "says": says, "link": link_for(t["token"])})
    return out


def passed(tests: list[dict]) -> dict | None:
    """The test that answers the requirement: passed, and read by somebody here."""
    for t in tests:
        if t.get("result") == "pass" and t.get("reviewedon"):
            return t
    return None


__all__ = ["ITEMS", "EXTRAS", "RATINGS", "RESULTS", "VEHICLE_TYPES", "VALID_DAYS",
           "link_for", "create", "standing", "for_driver", "passed"]
