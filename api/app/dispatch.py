"""Who should take this trip, and why.

The office books a job and TripProof says which driver and which vehicle suit it. Everything
needed to answer that is already in the product and was built for other reasons:

  * the compliance engine knows who may lawfully drive today
  * `driverlocations` knows where they were last seen
  * `hos` knows how close they are to their hours
  * the vehicle record knows whether it has a lift and how many it seats

What this adds is the arithmetic, and - more importantly - the SENTENCE. A list ordered by a
score nobody can see is a list you have to trust; every candidate here carries the reasons it
is where it is, and anybody disagreeing can see what was weighed.

Nothing here books anything. It ranks, and the office chooses - including choosing somebody
the ranking put last, which it is allowed to do for reasons this code cannot know.
"""

from datetime import date, datetime, time, timedelta
from math import asin, cos, radians, sin, sqrt

from sqlalchemy.engine import Connection

from app import tripcheck
from app import facts as factset
from app import hos, rules
from app.db import row, rows, localnow

# What a passenger needs, and what a vehicle must have to carry them.
#
# The one list. `rates` reads its labels from here rather than keeping a second copy, because
# a service you can price and a service you can book have to be the same list - two of them
# drift the moment one is added to.
#
# Bariatric is its own level, not a surcharge on the standard one: it is a different base
# fare, a different mileage rate and different equipment, and a schedule that cannot say so
# cannot price the trip. NOTE: a vehicle has no bariatric capability field yet, so `lift`
# is all that is checked here and dispatch will offer any lift-equipped van for one. That is
# a gap in the vehicle record, not in the pricing.
SERVICE = {
    "ambulatory": {"lift": False, "label": "Ambulatory"},
    "wheelchair": {"lift": True, "label": "Wheelchair"},
    "bariwheelchair": {"lift": True, "label": "Bariatric Wheelchair"},
    "stretcher": {"lift": True, "label": "Stretcher"},
    "baristretcher": {"lift": True, "label": "Bariatric Stretcher"},
}

# Beyond this a driver is not realistically the right answer for a pickup, however free they
# are. It is a sort order, not a rule - the office can still choose them.
FAR_MILES = 40.0
# A position older than this says where somebody was, not where they are.
STALE = timedelta(hours=2)


def _miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = radians(a[0]), radians(a[1]), radians(b[0]), radians(b[1])
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * asin(sqrt(h))


def _because(stop: dict) -> str:
    """Why this one is stopped, in words rather than as the title of a rule.

    The engine already writes a sentence for every requirement - "A defect reported on this
    vehicle has not been corrected and certified" - and the name on its own says nothing: a
    dispatcher reading "Cannot be dispatched - driver vehicle inspection reports" learns only
    which heading to go and look under. The first sentence of the reason is what belongs on a
    row this narrow; the rest is on the vehicle's own page.
    """
    said = (stop.get("why") or "").strip()
    if said:
        first = said.split(". ")[0].strip().rstrip(".")
        if first:
            return first
    return stop["name"]


# How long a leg is assumed to take when nobody has said. Only work that has NOT been driven can
# make somebody busy, and work not yet driven has no drop-off time - so without an allowance the
# query reads "until further notice" and a driver with a trip booked for noon is busy for the rest
# of their career.
LEG_ALLOWANCE = timedelta(minutes=90)


def _busy(conn: Connection, accountid: str, when: datetime, minutes: int,
          exceptleg: str | None = None) -> dict[str, str]:
    """Drivers and vehicles already committed across the window, and to what.

    Committed means WORK STILL TO DO. A completed leg does not hold anybody: the trip happened,
    the driver is free, and a van that carried somebody this morning is available this afternoon.
    This asked only about times, so a trip finished at 13:56 went on reserving its driver against
    every booking that overlapped it - including ones made afterwards.

    And a leg cannot clash with itself. Asking who is free for THIS leg has to leave this leg out,
    or the driver and the van already on it are reported as busy - with the very trip they are
    being considered for. That made the commonest change of all impossible: a van breaks down, a
    replacement is brought out, and the dispatcher wants to keep the driver and change only the
    vehicle. Tim came back "on trip TP-...B01A08 at that time", which is where he was supposed
    to be.
    """
    until = when + timedelta(minutes=minutes)
    taken: dict[str, str] = {}
    for leg in rows(conn, """
        SELECT l.driverid, l.vehicleid, l.pickupat, l.dropoffat, t.externalid
        FROM triplegs l
        JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        WHERE l.accountid = :a AND l.pickupat < :until
          AND (:notleg IS NULL OR l.recordid <> :notleg)
          AND l.executionstate <> 'completed' AND l.outcomestate IS NULL
          AND COALESCE(l.dropoffat, l.pickupat + INTERVAL :allow MINUTE) > :when
    """, a=accountid, when=when, until=until, notleg=exceptleg,
        allow=int(LEG_ALLOWANCE.total_seconds() // 60)):
        for who in (leg["driverid"], leg["vehicleid"]):
            if who:
                taken[who] = leg["externalid"]
    return taken


def drivers_for(conn: Connection, accountid: str, *, when: datetime, minutes: int,
                pickup: tuple[float, float] | None = None,
                exceptleg: str | None = None) -> list[dict]:
    """Every driver, ranked for this job, each saying why.

    Order: the ones who can go, nearest first; then the ones who could but should not; then
    the ones who may not at all. Nobody is hidden - "why is Tim not on this list" is a
    question the dispatcher will ask, and the answer has to be on the screen.
    """
    today = when.date() if isinstance(when, datetime) else date.today()
    committed = _busy(conn, accountid, when, minutes, exceptleg)
    seen = _last_seen(conn, accountid)
    roster = working(conn, accountid, when)
    out = []
    for d in rows(conn, """
        SELECT recordid, TRIM(CONCAT(COALESCE(firstname, ''), ' ', COALESCE(lastname, ''))) AS name,
               status
        FROM drivers WHERE accountid = :a AND deleted IS NULL
        ORDER BY lastname, firstname
    """, a=accountid):
        why, blocks = [], []

        # May they drive at all? The compliance engine owns this question; dispatch does not
        # get a second opinion on it.
        if d["status"] != "hired":
            blocks.append(f"Not hired - {d['status']}")
        else:
            f = factset.assemble(conn, accountid, d["recordid"])["facts"]
            stops = [r for r in rules.for_driver(conn, accountid, d["recordid"], f)
                     if r["applies"] and r["gate"] == "hardstop"
                     and r["status"] in ("expired", "failed", "overdue")]
            if stops:
                blocks.append(f"May not drive - {_because(stops[0])}")
            else:
                why.append("Qualified to drive")

        if d["recordid"] in committed:
            blocks.append(f"On trip {committed[d['recordid']]} at that time")
        elif not blocks:
            why.append("Free at that time")

        # Hours are a warning, not a bar: 14-90.006 is the company's to manage, and a
        # dispatcher looking at a near-limit driver may still have no alternative.
        warn = []
        off = roster.get(d["recordid"])
        if off:
            warn.append(off)
        standing = hos.standing(conn, accountid, d["recordid"], today)
        if standing and standing["determination"] == "hoursexceeded":
            warn.append("Over hours in the last week")
        elif standing:
            warn.append(f"{hos.hours(standing['weektotal'])} on duty this week")

        where = seen.get(d["recordid"])
        miles = None
        if pickup and where and where["fresh"]:
            miles = round(_miles(pickup, (where["lat"], where["lng"])), 1)
            why.append(f"{miles} mi from the pickup")
        elif where:
            why.append("Last position is stale")
        else:
            why.append("No position reported")

        out.append({
            "driverid": d["recordid"], "name": d["name"],
            "available": not blocks,
            "blocked": blocks, "because": why, "warnings": warn,
            "miles": miles,
        })
    # Available first, then nearest, then those with a known position, then by name.
    out.sort(key=lambda x: (not x["available"], bool(x["warnings"]),
                            x["miles"] if x["miles"] is not None else FAR_MILES * 2,
                            x["name"]))
    return out


# Monday first, because a working week starts on Monday everywhere this is read.
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def working(conn: Connection, accountid: str, when: datetime) -> dict[str, str | None]:
    """Who is rostered at this moment, and what to say about the ones who are not.

    A driver with no shifts recorded at all is treated as available, and says nothing. The day
    this table arrived every existing driver had no rows in it, and a feature that quietly makes
    the whole roster unavailable is worse than no feature.

    Being off-shift is a WARNING and never a bar. The hours are the company's own arrangement
    with its own staff; a dispatcher covering an emergency at six on a Sunday may know perfectly
    well that Maria will come in, and the software is not the party to that conversation.
    """
    weekday = when.weekday()
    clock = when.time()
    said: dict[str, str | None] = {}
    rostered: set[str] = set()
    has_any: set[str] = set()
    for s in rows(conn, """
        SELECT driverid, weekday, startsat, endsat FROM drivershifts
        WHERE accountid = :a
          AND (effectivefrom IS NULL OR effectivefrom <= :on)
          AND (effectiveto IS NULL OR effectiveto >= :on)
    """, a=accountid, on=when.date()):
        has_any.add(s["driverid"])
        start, end = _as_time(s["startsat"]), _as_time(s["endsat"])
        overnight = end <= start
        # A night turn belongs to the day it STARTED, so 01:00 on Tuesday is covered by Monday's
        # 22:00-06:00 shift and not by a Tuesday one.
        if s["weekday"] == weekday and (clock >= start if overnight else start <= clock < end):
            rostered.add(s["driverid"])
        if overnight and s["weekday"] == (weekday - 1) % 7 and clock < end:
            rostered.add(s["driverid"])
    for driverid in has_any:
        said[driverid] = None if driverid in rostered else "Not working at that time"
    return said


def _as_time(v):
    """MySQL hands a TIME back as a timedelta; the comparison wants a time."""
    if hasattr(v, "total_seconds"):
        total = int(v.total_seconds())
        return time(total // 3600 % 24, total // 60 % 60, total % 60)
    return v


def _last_seen(conn: Connection, accountid: str) -> dict[str, dict]:
    held = {}
    for r in rows(conn, """
        SELECT l.driverid, l.latitude, l.longitude, l.recordedon
        FROM driverlocations l
        JOIN (SELECT driverid, MAX(recordedon) AS newest FROM driverlocations
              WHERE accountid = :a GROUP BY driverid) n
          ON n.driverid = l.driverid AND n.newest = l.recordedon
        WHERE l.accountid = :a
    """, a=accountid):
        held[r["driverid"]] = {
            "lat": float(r["latitude"]), "lng": float(r["longitude"]),
            "when": r["recordedon"],
            "fresh": (datetime.utcnow() - r["recordedon"]) < STALE,
        }
    return held


def vehicles_for(conn: Connection, accountid: str, *, when: datetime, minutes: int,
                 exceptleg: str | None = None,
                 service: str = "ambulatory", seats: int = 1) -> list[dict]:
    """Every vehicle, ranked for this job, each saying why.

    The compliance engine owns whether a van may go out, exactly as it owns whether a driver may
    drive. This did not ask it: it checked the lift, the seats and whether the vehicle was already
    busy, and nothing else - so a vehicle whose own page read "a defect has not been corrected;
    49 CFR 396.11(c): it must not be dispatched" was offered to a dispatcher as available, and
    assigning it was allowed. The file said one thing and the board did another.
    """
    today = when.date() if isinstance(when, datetime) else date.today()
    needs = SERVICE.get(service, SERVICE["ambulatory"])
    committed = _busy(conn, accountid, when, minutes, exceptleg)
    out = []
    for v in rows(conn, """
        SELECT recordid, externalid, make, model, modelyear, seats, lift
        FROM vehicles WHERE accountid = :a AND deleted IS NULL
        ORDER BY externalid
    """, a=accountid):
        why, blocks = [], []

        # May it go out at all? The same question, asked of the same engine, in the same words
        # the vehicle's own file uses.
        f = factset.assemble(conn, accountid, vehicleid=v["recordid"])["facts"]
        stops = [r for r in rules.for_vehicle(conn, accountid, v["recordid"], f, today=today)
                 if r["applies"] and r["gate"] == "hardstop"
                 and r["status"] in ("expired", "failed", "overdue")]
        if stops:
            blocks.append(f"Cannot be dispatched - {_because(stops[0])}")
        else:
            why.append("Cleared to dispatch")
        if needs["lift"] and not v["lift"]:
            blocks.append(f"No lift - {needs['label'].lower()} service needs one")
        elif needs["lift"]:
            why.append("Has a lift")
        if v["seats"] is not None and seats and v["seats"] < seats:
            blocks.append(f"Seats {v['seats']}, needs {seats}")
        elif v["seats"]:
            why.append(f"Seats {v['seats']}")
        if v["recordid"] in committed:
            blocks.append(f"On trip {committed[v['recordid']]} at that time")
        elif not blocks:
            why.append("Free at that time")
        out.append({
            "vehicleid": v["recordid"],
            "name": f"{v['externalid']} · {v['make'] or ''} {v['model'] or ''}".strip(" ·"),
            "available": not blocks, "blocked": blocks, "because": why,
        })
    out.sort(key=lambda x: (not x["available"], x["name"]))
    return out


def best(conn: Connection, accountid: str, **terms) -> dict:
    """The ranked lists, and the pair the office would get if it pressed nothing.

    `trip` is the trip being booked - its payer and where it goes - so the suggestion is put to
    the same trip check the assignment will be. Without it, only who may drive at all is known."""
    who = drivers_for(conn, accountid, when=terms["when"], minutes=terms["minutes"],
                      pickup=terms.get("pickup"))
    what = vehicles_for(conn, accountid, when=terms["when"], minutes=terms["minutes"],
                        service=terms.get("service", "ambulatory"),
                        seats=terms.get("seats", 1))
    if terms.get("trip"):
        _judge(conn, accountid, who, what, leg=terms["trip"], when=terms["when"],
               service=terms.get("service", "ambulatory"))
    pick = next((d for d in who if d["available"] and not d["warnings"]),
                next((d for d in who if d["available"]), None))
    van = next((v for v in what if v["available"]), None)
    return {
        "drivers": who, "vehicles": what,
        "suggested": {"driverid": pick["driverid"] if pick else None,
                      "vehicleid": van["vehicleid"] if van else None},
    }


# ------------------------------------------------------------------------------------------------
# One leg, and who may take it
# ------------------------------------------------------------------------------------------------
# `drivers_for` answers "may this person drive today" - a question about the driver alone, which is
# why it can be asked before a trip exists. This answers the narrower and more useful one: may this
# person drive THIS leg, in THIS vehicle, for THIS broker, at THIS time.
#
# The difference is not decoration. A driver qualified to drive is not necessarily qualified for a
# Modivcare wheelchair run: the broker's own rule set may ask for training the federal one does not,
# the vehicle decides which license class is needed, and a requirement that lapsed last week may
# still have been valid on the pickup date of a trip being covered retrospectively.
#
# Nothing is evaluated twice. `tripcheck.check` is the same function the evaluator uses to decide
# whether a trip was compliant, and an assignment uses to allow it; here it is handed a leg that has
# not happened yet, with a candidate in it. Dispatch gets no second opinion on who may drive, and cannot drift from the engine that
# will later be asked to prove it.
def zone(conn: Connection, accountid: str) -> str:
    """The company's own wall clock. Pickup times are stored in it, so every question about
    whether something has happened yet has to be asked in it too."""
    return (row(conn, "SELECT timezone FROM accounts WHERE recordid = :a", a=accountid)
            or {}).get("timezone") or "America/New_York"


def for_leg(conn: Connection, accountid: str, legid: str) -> dict:
    leg = row(conn, """
        SELECT l.recordid AS legid, l.tripid, l.driverid, l.vehicleid, l.pickupat, l.dropoffat,
               l.pickuplat, l.pickuplng, l.signature, l.gps, l.servicelevel AS legservice,
               l.pickupplace, l.dropoffplace,
               t.externalid, t.brokerid, t.servicelevel, t.billedamount, t.passenger
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        WHERE l.recordid = :id AND l.accountid = :a
    """, id=legid, a=accountid)
    if not leg:
        return {}
    # A will-call return has no pickup time yet. Everything time-based - who is free, who is near -
    # is unanswerable until it is released, so the question is asked as of now and said to be.
    when = leg["pickupat"] or localnow(zone(conn, accountid))
    minutes = 60
    if leg["pickupat"] and leg["dropoffat"]:
        minutes = max(15, int((leg["dropoffat"] - leg["pickupat"]).total_seconds() // 60))
    service = leg["legservice"] or leg["servicelevel"] or "ambulatory"
    pickup = ((leg["pickuplat"], leg["pickuplng"])
              if leg["pickuplat"] is not None and leg["pickuplng"] is not None else None)

    drivers = drivers_for(conn, accountid, when=when, minutes=minutes, pickup=pickup,
                          exceptleg=legid)
    vehicles = vehicles_for(conn, accountid, when=when, minutes=minutes, service=service,
                            seats=1, exceptleg=legid)

    _judge(conn, accountid, drivers, vehicles, leg=leg, when=when, service=service)

    return {
        "leg": {k: leg[k] for k in ("legid", "tripid", "externalid", "passenger", "pickupat",
                                    "dropoffat", "driverid", "vehicleid")},
        "service": service, "servicelabel": SERVICE.get(service, SERVICE["ambulatory"])["label"],
        "released": leg["pickupat"] is not None,
        "drivers": drivers, "vehicles": vehicles,
    }


def _judge(conn: Connection, accountid: str, drivers: list[dict], vehicles: list[dict], *,
           leg: dict, when: datetime, service: str) -> None:
    """Put every candidate to the trip check an assignment goes through, and add what it fails.

    `leg` is a leg on file (it has a legid) or one being booked. A failure is a block, not a
    warning: a trip run by somebody who does not meet its requirements is a trip that cannot be
    billed, and offering it as a choice with a caution beside it is offering somebody a loss.
    Decided, not recorded - nobody has assigned anyone."""
    legid = leg.get("legid")
    states = tripcheck.trip_states(leg)

    def driver_blocks(candidate: str) -> list[str]:
        said = tripcheck.check(conn, accountid, candidate, None, legid=legid,
                               proposed=None if legid else leg, at=when, record=False)
        # The vehicle's own problems are the vehicle's, shown against it rather than every driver;
        # and whether they are hired is already said by the candidate list itself.
        return [b.get("reason") or b.get("name") or b["code"] for b in said["blockers"]
                if not b.get("vehicle") and b["code"] not in ("HIRED", "DRIVER")]

    away = _unavailable(conn, accountid, when)
    for d in drivers:
        d["blocked"] = d["blocked"] + driver_blocks(d["driverid"])
        if d["driverid"] in away["drivers"]:
            d["warnings"] = d["warnings"] + [away["drivers"][d["driverid"]]]
        d["available"] = not d["blocked"]
    for v in vehicles:
        v["blocked"] = v["blocked"] + [
            b.get("reason") or b.get("name") or b["code"]
            for b in tripcheck.vehicle_blockers(conn, accountid, v["vehicleid"], service, when, states)]
        v.setdefault("warnings", [])
        if v["vehicleid"] in away["vehicles"]:
            v["warnings"] = v["warnings"] + [away["vehicles"][v["vehicleid"]]]
        v["available"] = not v["blocked"]
    # The same order drivers_for gives - nearest first among equals - with the check's answer in it.
    drivers.sort(key=lambda x: (not x["available"], bool(x["warnings"]),
                                x["miles"] if x.get("miles") is not None else FAR_MILES * 2,
                                x["name"]))
    vehicles.sort(key=lambda x: (not x["available"], bool(x["warnings"]), x["name"]))


def _unavailable(conn: Connection, accountid: str, when: datetime) -> dict:
    """Who has told us they cannot work, and what is off the road. A warning rather than a bar:
    time off is the company's own record of its own arrangements, and a dispatcher covering a
    Saturday emergency may know something the calendar does not."""
    out = {"drivers": {}, "vehicles": {}}
    for r in rows(conn, """
        SELECT driverid AS who, reason FROM driverunavailable
        WHERE accountid = :a AND fromat <= :when AND untilat > :when
    """, a=accountid, when=when):
        out["drivers"][r["who"]] = f"Marked unavailable - {r['reason']}"
    for r in rows(conn, """
        SELECT vehicleid AS who, reason FROM vehicleunavailable
        WHERE accountid = :a AND fromat <= :when AND untilat > :when
    """, a=accountid, when=when):
        out["vehicles"][r["who"]] = f"Off the road - {r['reason']}"
    return out
