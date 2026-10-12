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

from datetime import date, datetime, timedelta
from math import asin, cos, radians, sin, sqrt

from sqlalchemy.engine import Connection

from app import facts as factset
from app import hos, rules
from app.db import row, rows

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


def _busy(conn: Connection, accountid: str, when: datetime, minutes: int) -> dict[str, str]:
    """Drivers and vehicles already committed across the window, and to what."""
    until = when + timedelta(minutes=minutes)
    taken: dict[str, str] = {}
    for leg in rows(conn, """
        SELECT l.driverid, l.vehicleid, l.pickupat, l.dropoffat, t.externalid
        FROM triplegs l
        JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        WHERE l.accountid = :a AND l.pickupat < :until
          AND (l.dropoffat IS NULL OR l.dropoffat > :when)
    """, a=accountid, when=when, until=until):
        for who in (leg["driverid"], leg["vehicleid"]):
            if who:
                taken[who] = leg["externalid"]
    return taken


def drivers_for(conn: Connection, accountid: str, *, when: datetime, minutes: int,
                pickup: tuple[float, float] | None = None) -> list[dict]:
    """Every driver, ranked for this job, each saying why.

    Order: the ones who can go, nearest first; then the ones who could but should not; then
    the ones who may not at all. Nobody is hidden - "why is Tim not on this list" is a
    question the dispatcher will ask, and the answer has to be on the screen.
    """
    today = when.date() if isinstance(when, datetime) else date.today()
    committed = _busy(conn, accountid, when, minutes)
    seen = _last_seen(conn, accountid)
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
                blocks.append(f"May not drive - {stops[0]['name'].lower()}")
            else:
                why.append("Qualified to drive")

        if d["recordid"] in committed:
            blocks.append(f"On trip {committed[d['recordid']]} at that time")
        elif not blocks:
            why.append("Free at that time")

        # Hours are a warning, not a bar: 14-90.006 is the company's to manage, and a
        # dispatcher looking at a near-limit driver may still have no alternative.
        warn = []
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
                 service: str = "ambulatory", seats: int = 1) -> list[dict]:
    """Every vehicle, ranked for this job, each saying why."""
    needs = SERVICE.get(service, SERVICE["ambulatory"])
    committed = _busy(conn, accountid, when, minutes)
    out = []
    for v in rows(conn, """
        SELECT recordid, externalid, make, model, modelyear, seats, lift
        FROM vehicles WHERE accountid = :a AND deleted IS NULL
        ORDER BY externalid
    """, a=accountid):
        why, blocks = [], []
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
    """The ranked lists, and the pair the office would get if it pressed nothing."""
    who = drivers_for(conn, accountid, when=terms["when"], minutes=terms["minutes"],
                      pickup=terms.get("pickup"))
    what = vehicles_for(conn, accountid, when=terms["when"], minutes=terms["minutes"],
                        service=terms.get("service", "ambulatory"),
                        seats=terms.get("seats", 1))
    pick = next((d for d in who if d["available"] and not d["warnings"]),
                next((d for d in who if d["available"]), None))
    van = next((v for v in what if v["available"]), None)
    return {
        "drivers": who, "vehicles": what,
        "suggested": {"driverid": pick["driverid"] if pick else None,
                      "vehicleid": van["vehicleid"] if van else None},
    }
