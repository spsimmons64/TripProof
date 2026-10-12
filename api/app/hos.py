###################################################################################################
# Hours of service under F.A.C. 14-90.006.
#
# This is not a document. FDOT issues no hours-of-service form and asks for none: 14-90.006(3) and
# (5) are limits on what a driver may actually do, and the guidance is to review the driver's
# schedules and work records to see whether the limits were kept. So what is held here is the work
# itself - a row per driver per day - and the requirement is answered by arithmetic over those
# rows rather than by somebody uploading a PDF called "hours of service".
#
# THE LIMITS, as 14-90.006 states them:
#
#   (3)  no more than 12 hours DRIVING in any 24-hour period
#        no driving after 16 hours ON DUTY in any 24-hour period
#   (5)  no more than 72 hours ON DUTY in any 7 consecutive days
#
# The seven-day limit is a ROLLING one. It is not "72 hours Monday to Sunday" - every day is the
# end of its own seven-day window, and a driver can keep every single week under 72 hours and
# still break it across a weekend. So the check walks each day and looks back over the previous
# six, which is the only reading that catches that.
#
# Where the numbers come from is recorded against each day. TripProof can fill them from dispatch
# once trips are being imported; until then, and for any work done outside the trip workflow -
# a yard shift, a vehicle moved, a day driving for somebody else - they are entered by hand. A
# limit that only counts the work TripProof happens to know about is not a limit.
###################################################################################################
from datetime import date, timedelta

from sqlalchemy.engine import Connection

from app.db import rows

DRIVING_LIMIT = 12 * 60        # 14-90.006(3)
DUTY_LIMIT = 16 * 60           # 14-90.006(3)
WEEK_LIMIT = 72 * 60           # 14-90.006(5)
WEEK_DAYS = 7
# How far back the requirement looks when deciding whether a driver is within the limits now. A
# breach last March is history; a breach this week is a driver who should not be driving.
LOOKBACK = timedelta(days=30)


def hours(minutes) -> str:
    """Minutes as the rule speaks: 12 h, 12 h 30."""
    m = int(minutes or 0)
    return f"{m // 60} h" + (f" {m % 60:02d}" if m % 60 else "")


def days_for(conn: Connection, accountid: str, driverid: str, since: date | None = None,
             until: date | None = None) -> list[dict]:
    """The duty days on file for this driver, oldest first."""
    return rows(conn, """
        SELECT recordid, dutydate, dutystart, dutyend, drivingminutes, ondutyminutes,
               source, note
        FROM driverdutydays
        -- Both: `deleted` is what days removed before withdrawal had a reason were marked with,
        -- and those stay removed. Everything from here uses the one word.
        WHERE accountid = :a AND driverid = :d AND deleted IS NULL AND withdrawn IS NULL
          AND (:since IS NULL OR dutydate >= :since)
          AND (:until IS NULL OR dutydate <= :until)
        ORDER BY dutydate
    """, a=accountid, d=driverid, since=since, until=until)


def breaches(days: list[dict]) -> list[dict]:
    """Every day on which a limit was exceeded, and which limit it was.

    One day can break more than one - a driver who is on duty nineteen hours and drives thirteen
    of them has broken both of 14-90.006(3)'s limits, and saying only the first would understate
    what happened.
    """
    byday = {d["dutydate"]: d for d in days}
    out = []
    for d in days:
        said = []
        if (d["drivingminutes"] or 0) > DRIVING_LIMIT:
            said.append(f'drove {hours(d["drivingminutes"])} in a 24-hour period, '
                        f'over the {hours(DRIVING_LIMIT)} limit')
        if (d["ondutyminutes"] or 0) > DUTY_LIMIT:
            said.append(f'on duty {hours(d["ondutyminutes"])} in a 24-hour period, '
                        f'over the {hours(DUTY_LIMIT)} limit')
        # The rolling week ENDING on this day, which is the window 14-90.006(5) actually sets.
        window = sum((byday[d["dutydate"] - timedelta(days=n)]["ondutyminutes"] or 0)
                     for n in range(WEEK_DAYS)
                     if d["dutydate"] - timedelta(days=n) in byday)
        if window > WEEK_LIMIT:
            said.append(f'on duty {hours(window)} in the 7 days ending that day, '
                        f'over the {hours(WEEK_LIMIT)} limit')
        for why in said:
            out.append({"dutydate": d["dutydate"], "why": why})
    return out


def week_total(days: list[dict], ending: date) -> int:
    """On-duty minutes in the seven consecutive days ending on `ending`."""
    byday = {d["dutydate"]: (d["ondutyminutes"] or 0) for d in days}
    return sum(byday.get(ending - timedelta(days=n), 0) for n in range(WEEK_DAYS))


def standing(conn: Connection, accountid: str, driverid: str,
             today: date | None = None) -> dict | None:
    """Where this driver stands against 14-90.006, from the work on file.

    `None` where nothing has been recorded at all - which is not compliance and is not a breach,
    it is an empty record, and the requirement says so in its own words.
    """
    today = today or date.today()
    # A day's seven-day window reaches back six days before it, so the window itself has to be
    # loaded or the rolling total is computed off a truncated history.
    days = days_for(conn, accountid, driverid,
                    since=today - LOOKBACK - timedelta(days=WEEK_DAYS))
    if not days:
        return None
    recent = [d for d in days if d["dutydate"] >= today - LOOKBACK]
    over = [b for b in breaches(days) if b["dutydate"] >= today - LOOKBACK]
    last = max(d["dutydate"] for d in days)
    return {"recordid": f"{driverid}:hos", "effectiveon": last, "expireson": None, "exempt": 0,
            "documentid": None, "sourcetable": "driverdutydays",
            "days": len(recent), "lastday": last, "breaches": over,
            "weektotal": week_total(days, last),
            "determination": "hoursexceeded" if over else "withinlimits"}
