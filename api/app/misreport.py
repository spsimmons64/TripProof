###################################################################################################
# The drug and alcohol testing MIS report - 49 CFR 382.403, Part 40 Appendix J.
#
# Appendix J, not H. The form moved at 88 FR 27651 on 2 May 2023 and a good deal of the
# writing about it still says H, which is how it ended up saying H here.
#
# What the carrier sends FMCSA when it is asked for it: how many covered employees it had, and
# every test it conducted in the calendar year, split by what the test was for, why it was given
# and what came back.
#
# This does not produce the form. The form is a government document with its own layout and its
# own submission route, and inventing a lookalike would invite somebody to send ours instead of
# theirs. What this produces is the FIGURES - every box, counted off the records that are already
# here, so filling the real form is reading numbers across rather than counting rows by hand at
# the end of a year and hoping.
#
# TWO THINGS IT REFUSES TO DO
#
# It does not guess at a test whose type was never recorded. Those are counted and reported as
# unrecorded rather than folded into the controlled substances column, because a figure sent to
# FMCSA that nobody can trace back is worse than a gap somebody can go and fill.
#
# And it counts a cancelled test as cancelled. 40.23(f): a cancelled test is not a test - it is
# neither positive nor negative - so it has its own line on the form and never joins a total it
# would distort.
###################################################################################################
from datetime import date
from decimal import Decimal

from sqlalchemy.engine import Connection

from app import randompool
from app.db import rows

# The order the form asks for them in, which is not alphabetical and not the order anybody
# would choose - but a figure in the wrong box is a wrong figure.
REASONS = ["preemployment", "random", "postaccident", "reasonablesuspicion",
           "returntoduty", "followup"]
REASON_SAYS = {
    "preemployment": "Pre-employment",
    "random": "Random",
    "postaccident": "Post-accident",
    "reasonablesuspicion": "Reasonable suspicion",
    "returntoduty": "Return-to-duty",
    "followup": "Follow-up",
}

# 382.505 puts a driver off duty for 24 hours at 0.02; 382.507 makes 0.04 a violation. The form
# counts the two bands separately and everything under 0.02 as a negative.
ALCOHOL_BANDS = [("under02", Decimal("0.02")), ("band0202", Decimal("0.04"))]


def _band(bac) -> str:
    if bac is None:
        return "unrecorded"
    value = Decimal(str(bac))
    if value < Decimal("0.02"):
        return "under02"
    if value < Decimal("0.04"):
        return "band0202"
    return "band04"


def _blank_drug() -> dict:
    return {"tests": 0, "negative": 0, "positive": 0, "refusal": 0, "cancelled": 0,
            "pending": 0, "substances": {}}


def _blank_alcohol() -> dict:
    return {"tests": 0, "under02": 0, "band0202": 0, "band04": 0, "refusal": 0,
            "cancelled": 0, "pending": 0, "unrecorded": 0}


def collect(conn: Connection, accountid: str, year: int) -> dict:
    """Every figure the MIS form asks for, for one calendar year."""
    held = rows(conn, """
        SELECT reason, result, testtype, substance, bac
        FROM drugtests
        WHERE accountid = :a AND withdrawn IS NULL
          AND collectedon >= :from AND collectedon <= :to
    """, a=accountid, **{"from": date(year, 1, 1), "to": date(year, 12, 31)})

    drug = {r: _blank_drug() for r in REASONS}
    alcohol = {r: _blank_alcohol() for r in REASONS}
    unrecorded, offform = 0, 0

    for t in held:
        reason = t["reason"]
        if reason not in REASONS:
            offform += 1
            continue
        kind = (t["testtype"] or "").lower()
        if kind not in ("drug", "alcohol"):
            unrecorded += 1
            continue
        result = (t["result"] or "").lower()
        if kind == "drug":
            box = drug[reason]
            box["tests"] += 1
            if result in ("negative", "negativedilute"):
                box["negative"] += 1
            elif result == "positive":
                box["positive"] += 1
                # The form counts each drug found, and one specimen can be positive for
                # several, so a test contributes to more than one line.
                for drugname in [x.strip() for x in (t["substance"] or "").split(",")
                                 if x.strip()]:
                    box["substances"][drugname] = (
                        box["substances"].get(drugname, 0) + 1)
            elif result in ("refusal", "adulterated", "substituted"):
                box["refusal"] += 1
            elif result == "cancelled":
                box["cancelled"] += 1
            elif result == "pending":
                box["pending"] += 1
        else:
            box = alcohol[reason]
            box["tests"] += 1
            if result in ("refusal", "adulterated", "substituted"):
                box["refusal"] += 1
            elif result == "cancelled":
                box["cancelled"] += 1
            elif result == "pending":
                box["pending"] += 1
            else:
                box[_band(t["bac"])] += 1

    # Part II. 382.305(b) and the MIS form both ask for the AVERAGE number of covered driver
    # positions across the year, not the headcount on the day somebody fills it in.
    start, end = randompool.window(conn, accountid, year, date(year, 12, 31))
    covered = randompool.average(conn, accountid, start, end)
    # No overlap at all - the pool began after this year ended - so there is nothing to say a
    # figure was counted from.
    counted_from = start if (start != date(year, 1, 1) and start <= end) else None

    return {
        "year": year,
        "covered": round(covered, 1),
        "coveredfrom": str(counted_from) if counted_from else None,
        "reasons": REASONS, "reasonsays": REASON_SAYS,
        "drug": drug, "alcohol": alcohol,
        "totals": {
            "drug": {k: sum(drug[r][k] for r in REASONS)
                     for k in ("tests", "negative", "positive", "refusal", "cancelled", "pending")},
            "alcohol": {k: sum(alcohol[r][k] for r in REASONS)
                        for k in ("tests", "under02", "band0202", "band04", "refusal",
                                  "cancelled", "pending", "unrecorded")},
        },
        # Said out loud rather than folded in. A number on a federal form that nobody can trace
        # back to a record is worse than a gap somebody can go and close.
        "unrecorded": unrecorded,
        "offform": offform,
    }


__all__ = ["collect", "REASONS", "REASON_SAYS"]
