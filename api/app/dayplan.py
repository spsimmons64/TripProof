"""Auto assignment: a driver, in the vehicle of their shift, for each of a day's unassigned trips.

Only drivers ON SHIFT at the pickup are considered, in the vehicle that shift gives them - the
shift is where the vehicle comes from. Every pairing is the one the Assign dialog would offer
(app/dispatch.for_leg judges it: the driver's qualification, the trip's own program, the vehicle
fitting the service level, nobody already on another trip), and only the clean ones: a pairing
that needs somebody's say-so is left for a person to make.

Of the drivers left, the one with the shortest empty run to the pickup - from where their last
trip that day drops off, or where their vehicle was last seen - with the day's work kept even:
each trip a driver already has counts as some miles against them. Trips are placed in pickup
order, and each placement is counted when the next is weighed, so nobody is given two trips at
once or one they cannot reach in time.

Nothing is saved here. The office looks at the proposal and saves it, and each assignment then
passes the same gate a hand-made one does (routers/trips.assign_leg).
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from sqlalchemy.engine import Connection

from app import dispatch, wheremap
from app import shifts as plan
from app.db import engine, rows

# How fast an empty vehicle is assumed to cross town, and how much longer the road is than the
# straight line. Rough on purpose: it decides whether a driver can get there, not when they will.
CITY_MPH = 25
ROAD_FACTOR = 1.3
# Each trip a driver already has that day weighs as this many miles of empty running: enough that
# work spreads out, not so much that somebody is sent across the county to even the count.
TRIP_WEIGHT = 8


def _drive_minutes(a, b) -> int:
    if not a or not b:
        return 0
    return int(dispatch._miles(a, b) * ROAD_FACTOR / CITY_MPH * 60)


def _ends(leg: dict) -> datetime:
    return leg["dropoffat"] or leg["pickupat"] + dispatch.LEG_ALLOWANCE


def _place(lat, lng):
    return (float(lat), float(lng)) if lat is not None and lng is not None else None


def unassigned(conn: Connection, accountid: str, day: date) -> list[dict]:
    """The day's legs with nobody on them that auto assignment can place: a pickup time that day,
    not canceled or closed, and work that is ours (not offered, not being handed back)."""
    return rows(conn, """
        SELECT l.recordid AS legid, l.pickupat, l.dropoffat, l.pickuplat, l.pickuplng,
               l.dropofflat, l.dropofflng, t.externalid, t.passenger
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        WHERE l.accountid = :a AND l.driverid IS NULL AND l.outcomestate IS NULL
          AND l.executionstate = 'scheduled' AND t.cancelledon IS NULL
          AND COALESCE(t.brokerstate, '') NOT IN ('offered', 'returnpending', 'returned')
          AND l.pickupat IS NOT NULL AND DATE(l.pickupat) = :d
        ORDER BY l.pickupat
    """, a=accountid, d=day)


def propose(conn: Connection, accountid: str, day: date) -> list[dict]:
    legs = unassigned(conn, accountid, day)
    if not legs:
        return []
    shifts = rows(conn, """
        SELECT s.driverid, s.vehicleid, s.startsat, s.endsat, v.externalid AS vehiclename,
               TRIM(CONCAT(d.firstname, ' ', d.lastname)) AS drivername
        FROM dayshifts s JOIN drivers d ON d.recordid = s.driverid
        JOIN vehicles v ON v.recordid = s.vehicleid
        WHERE s.accountid = :a AND s.workday = :w
    """, a=accountid, w=day)
    for s in shifts:
        s["from"], s["to"] = plan.span(day, s["startsat"], s["endsat"])

    # Each driver's day so far: the trips they already have, which the new ones must fit between.
    held: dict[str, list[dict]] = {}
    for l in rows(conn, """
        SELECT driverid, pickupat, dropoffat, pickuplat, pickuplng, dropofflat, dropofflng
        FROM triplegs WHERE accountid = :a AND driverid IS NOT NULL AND outcomestate IS NULL
          AND pickupat IS NOT NULL AND DATE(pickupat) = :d
    """, a=accountid, d=day):
        held.setdefault(l["driverid"], []).append(l)
    spots = plan._vehicle_spots(conn, accountid)
    # A vehicle never seen anywhere is taken to start the day at the company's own address.
    base = wheremap.base_of(conn, accountid) or {}
    home = ((float(base["latitude"]), float(base["longitude"]))
            if base.get("latitude") is not None and base.get("longitude") is not None else None)

    def covering(leg: dict) -> list[dict]:
        """The shifts that hold the whole trip, pickup to drop-off."""
        return [s for s in shifts if s["from"] <= leg["pickupat"] and _ends(leg) <= s["to"]]

    # What an assignment would say for each leg - only for the drivers on shift for it, each in
    # their shift's vehicle. Independent of one another, so asked in parallel, each on its own
    # connection.
    def judged(leg: dict) -> dict:
        on = covering(leg)
        if not on:
            return {}
        with engine.connect() as own:
            return dispatch.for_leg(own, accountid, leg["legid"], only={s["driverid"] for s in on},
                                    vehicle_of={s["driverid"]: s["vehicleid"] for s in on})

    with ThreadPoolExecutor(max_workers=4) as pool:
        said = dict(zip([l["legid"] for l in legs], pool.map(judged, legs)))

    out = []
    for leg in legs:
        start, end = leg["pickupat"], _ends(leg)
        pickup = _place(leg["pickuplat"], leg["pickuplng"])
        drivers = {d["driverid"]: d for d in said[leg["legid"]].get("drivers", [])}
        vehicles = {v["vehicleid"]: v for v in said[leg["legid"]].get("vehicles", [])}
        on = covering(leg)
        best, why_not = None, []
        for s in on:
            d, v = drivers.get(s["driverid"]), vehicles.get(s["vehicleid"])
            who = s["drivername"].title()
            if not d or d["blocked"]:
                why_not.append(f"{who}: {(d or {}).get('blocked', ['Not found'])[0]}")
                continue
            if not v or v["blocked"]:
                why_not.append(f"{who}: {s['vehiclename']} - {(v or {}).get('blocked', ['Not found'])[0]}")
                continue
            if d["warnings"] or v.get("warnings"):
                why_not.append(f"{who}: {(d['warnings'] + v.get('warnings', []))[0]} - needs a person's say-so")
                continue
            # Fits between the trips they already have, with time to drive between them.
            mine = sorted(held.get(s["driverid"], []), key=lambda x: x["pickupat"])
            before = [x for x in mine if x["pickupat"] <= start]
            after = [x for x in mine if x["pickupat"] > start]
            last = before[-1] if before else None
            if last and _ends(last) + timedelta(minutes=_drive_minutes(
                    _place(last["dropofflat"], last["dropofflng"]), pickup)) > start:
                why_not.append(f"{who}: cannot get there from the trip before")
                continue
            if after and end + timedelta(minutes=_drive_minutes(
                    _place(leg["dropofflat"], leg["dropofflng"]),
                    _place(after[0]["pickuplat"], after[0]["pickuplng"]))) > after[0]["pickupat"]:
                why_not.append(f"{who}: would be late for the trip after")
                continue
            here = (_place(last["dropofflat"], last["dropofflng"]) if last
                    else spots.get(s["vehicleid"]) or home)
            empty = round(dispatch._miles(here, pickup), 1) if here and pickup else None
            score = (empty if empty is not None else 15) + TRIP_WEIGHT * len(mine)
            if best is None or score < best[0]:
                reasons = [f"On shift in {s['vehiclename']}"]
                if empty is not None:
                    reasons.append(f"{empty} mi from {'the last drop-off' if last else 'where the vehicle is' if s['vehicleid'] in spots else 'the base'}")
                reasons.append(f"{len(mine) + 1} trip{'s' if mine else ''} today")
                best = (score, s, reasons)
        item = {"legid": leg["legid"], "externalid": leg["externalid"], "passenger": leg["passenger"],
                "pickupat": leg["pickupat"], "driverid": None, "vehicleid": None,
                "drivername": None, "vehiclename": None, "reasons": [], "blocked": []}
        if best:
            _, s, reasons = best
            item.update(driverid=s["driverid"], vehicleid=s["vehicleid"], drivername=s["drivername"],
                        vehiclename=s["vehiclename"], reasons=reasons)
            held.setdefault(s["driverid"], []).append(leg)
        else:
            item["blocked"] = why_not or ["Nobody is on shift for the whole trip"]
        out.append(item)
    return out


def day_vehicle(conn: Connection, accountid: str, driverid: str, day: date,
                when: datetime | None = None) -> dict | None:
    """The vehicle this driver has that day, for a trip a dispatcher has put on them. The vehicle
    assignment says which vehicle, not when they may work - the dispatcher decides that. So the
    assignment holding the pickup if there is one, else the nearest to it that day; a will-call,
    with no time yet, the day's last (the return comes late)."""
    held = rows(conn, """
        SELECT s.vehicleid, s.startsat, s.endsat, v.externalid AS vehiclename FROM dayshifts s
        JOIN vehicles v ON v.recordid = s.vehicleid
        WHERE s.accountid = :a AND s.driverid = :d AND s.workday = :w
    """, a=accountid, d=driverid, w=day)
    if not held:
        return None
    for s in held:
        s["from"], s["to"] = plan.span(day, s["startsat"], s["endsat"])
    if when is None:
        return max(held, key=lambda s: s["to"])

    def gap(s: dict) -> float:
        if s["from"] <= when < s["to"]:
            return 0
        return min(abs((when - s["from"]).total_seconds()), abs((when - s["to"]).total_seconds()))
    return min(held, key=gap)
