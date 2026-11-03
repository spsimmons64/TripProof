"""Auto assignment: a driver, in the vehicle of their shift, for each of a day's unassigned trips.

Only drivers ON SHIFT at the pickup are considered, in the vehicle that shift gives them - the
shift is where the vehicle comes from. Every pairing is the one the Assign dialog would offer
(app/dispatch.for_leg judges it: the driver's qualification, the trip's own program, the vehicle
fitting the service level, nobody already on another trip), and only the clean ones: a pairing
that needs somebody's say-so is left for a person to make.

Of the drivers left, the one with the shortest empty run to the pickup - from where their last
trip that day drops off, or where their vehicle was last seen - with the day's work kept even:
each trip a driver already has counts as some miles against them. Each placement is counted when
the next is weighed, so nobody is given two trips at once or one they cannot reach in time.

Trips are placed most important first, so when there are not drivers enough for all of them it is
the least important that wait: a critical trip (dialysis, chemotherapy) before any other; then
every broker trip the company has accepted, by pickup time; then the rest by the company's ranking
of the payer (High, Normal, Low - Payers page, private pay included) and pickup time.

Accepted broker work is never put behind better-paying work. Brokers call that cherry-picking and
their manuals forbid it: once a trip is accepted it is the company's to run, and it gives way only
to a trip the passenger cannot miss. A broker's trip that lost its driver to a critical one says
which, and is one to hand back to the broker while there is time to run it.

Nothing is saved here. The office looks at the proposal and saves it, and each assignment then
passes the same gate a hand-made one does (routers/trips.assign_leg).
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from sqlalchemy.engine import Connection

from app import dispatch, wheremap
from app import shifts as plan
from app.db import engine, localnow, rows

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
    return leg["pickupat"] + timedelta(minutes=dispatch.leg_minutes(leg))


# A pickup this close is placed before later ones: a trip at 2:30 left with nobody has nobody, while
# one at 4:30 still has two hours for somebody to be called in, or the trip moved or handed back.
DUE_SOON = timedelta(hours=2)


def priority_of(leg: dict) -> str:
    """How the trip reads in the plan: Critical, Due Soon, or confirmed at its time."""
    return "critical" if leg.get("critical") else "soon" if leg.get("soon") else "confirmed"


def _said(leg: dict) -> str:
    """Why a trip went first, in a few words: "a critical trip", "due within 2 hours", "booked first"."""
    return {"critical": "a critical trip", "soon": "due within 2 hours"}.get(priority_of(leg), "booked first")


# What _rank reads, for a leg selected as l joined to its trip t: whether it is critical, and when
# the trip was confirmed - booked, or a broker's offer accepted.
RANKED = "t.critical, t.brokerid, COALESCE(t.confirmedon, t.added) AS confirmedat"
PAYER = ""


def _rank(leg: dict) -> tuple:
    """Critical first; then a pickup within two hours (`soon`, set by the plan); then a confirmed
    trip keeps its place - the first confirmed placed first, and one confirmed later never takes its
    driver. The pickup time last, between two confirmed at the same moment."""
    return (0 if leg.get("critical") else 1, 0 if leg.get("soon") else 1,
            leg.get("confirmedat") or datetime.max, leg["pickupat"])


def _place(lat, lng):
    return (float(lat), float(lng)) if lat is not None and lng is not None else None


def unassigned(conn: Connection, accountid: str, day: date) -> list[dict]:
    """The day's legs with nobody on them that auto assignment can place: a pickup time that day,
    not canceled or closed, and work that is ours (not offered, not being handed back)."""
    return rows(conn, """
        SELECT l.recordid AS legid, l.pickupat, l.dropoffat, l.appointmentat, l.pickuplat, l.pickuplng,
               l.dropofflat, l.dropofflng, t.externalid, t.passenger, t.critical, t.brokerid,
               l.legnumber = 1 AND EXISTS (SELECT 1 FROM triplegs r WHERE r.tripid = l.tripid AND r.legnumber > 1
                   AND r.responsibility = 'unconfirmed' AND r.brokerstate IS NULL AND r.outcomestate IS NULL) AS undecided,
               COALESCE(t.confirmedon, t.added) AS confirmedat
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        WHERE l.accountid = :a AND l.driverid IS NULL AND l.outcomestate IS NULL
          AND l.executionstate = 'scheduled' AND t.cancelledon IS NULL
          AND COALESCE(t.brokerstate, '') NOT IN ('offered', 'returnpending', 'returned')
          AND l.brokerstate IS NULL
          AND l.pickupat IS NOT NULL AND DATE(l.pickupat) = :d
        ORDER BY l.pickupat
    """, a=accountid, d=day)


def propose(conn: Connection, accountid: str, day: date, only: set[str] | None = None) -> list[dict]:
    """`only` is the trips the dispatcher ticked; the rest are left for them to place by hand."""
    legs = [l for l in unassigned(conn, accountid, day) if only is None or l["legid"] in only]
    if not legs:
        return []
    soon = localnow(dispatch.zone(conn, accountid)).replace(tzinfo=None) + DUE_SOON
    for l in legs:
        l["soon"] = l["pickupat"] <= soon
    shifts = rows(conn, """
        SELECT s.driverid, s.vehicleid, s.startsat, s.endsat, s.oncall, v.externalid AS vehiclename,
               TRIM(CONCAT(d.firstname, ' ', d.lastname)) AS drivername
        FROM dayshifts s JOIN drivers d ON d.recordid = s.driverid
        JOIN vehicles v ON v.recordid = s.vehicleid
        WHERE s.accountid = :a AND s.workday = :w
    """, a=accountid, w=day) + plan.on_call(conn, accountid, day)
    for s in shifts:
        s["from"], s["to"] = plan.span(day, s["startsat"], s["endsat"])

    # Each driver's day so far: the trips they already have, which the new ones must fit between.
    held: dict[str, list[dict]] = {}
    for l in rows(conn, """
        SELECT driverid, pickupat, dropoffat, appointmentat, pickuplat, pickuplng, dropofflat, dropofflng
        FROM triplegs WHERE accountid = :a AND driverid IS NOT NULL AND outcomestate IS NULL
          AND pickupat IS NOT NULL AND DATE(pickupat) = :d
    """, a=accountid, d=day):
        held.setdefault(l["driverid"], []).append(l)
    spots = plan._vehicle_spots(conn, accountid)
    # A vehicle never seen anywhere is taken to start the day at the company's own address.
    base = wheremap.base_of(conn, accountid) or {}
    home = ((float(base["latitude"]), float(base["longitude"]))
            if base.get("latitude") is not None and base.get("longitude") is not None else None)

    # An on-call driver is kept for what comes after closing, not to take the day's work.
    from app.routers.shifts import company_hours
    h = company_hours(conn, accountid, day)
    closes = plan.span(day, h["open"], h["close"])[1] if h and not h.get("closed") else None

    def covering(leg: dict) -> list[dict]:
        """The shifts that hold the whole trip, pickup to drop-off."""
        return [s for s in shifts if s["from"] <= leg["pickupat"] and _ends(leg) <= s["to"]
                and (not s["oncall"] or closes is None or leg["pickupat"] >= closes)]

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
    for leg in sorted(legs, key=_rank):
        start, end = leg["pickupat"], _ends(leg)
        pickup = _place(leg["pickuplat"], leg["pickuplng"])
        drivers = {d["driverid"]: d for d in said[leg["legid"]].get("drivers", [])}
        vehicles = {v["vehicleid"]: v for v in said[leg["legid"]].get("vehicles", [])}
        on = covering(leg) if not leg.get("undecided") else []
        best, why_not, gave = None, [], []
        if leg.get("undecided"):
            why_not.append("Who brings the passenger home has not been decided (Edit Trip)")

        def lost_to(other: dict | None) -> bool:
            """Whether the trip in the way was placed ahead of this one for being more important -
            not merely earlier."""
            if other and other.get("legid") and _rank(other)[:3] < _rank(leg)[:3]:
                gave.append(other)
                return True
            return False
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
                why_not.append(f"{who}: Given to {last['passenger']}, {_said(last)}"
                               if lost_to(last) else f"{who}: cannot get there from the trip before")
                continue
            if after and end + timedelta(minutes=_drive_minutes(
                    _place(leg["dropofflat"], leg["dropofflng"]),
                    _place(after[0]["pickuplat"], after[0]["pickuplng"]))) > after[0]["pickupat"]:
                why_not.append(f"{who}: Given to {after[0]['passenger']}, {_said(after[0])}"
                               if lost_to(after[0]) else f"{who}: would be late for the trip after")
                continue
            here = (_place(last["dropofflat"], last["dropofflng"]) if last
                    else spots.get(s["vehicleid"]) or home)
            empty = round(dispatch._miles(here, pickup), 1) if here and pickup else None
            score = (empty if empty is not None else 15) + TRIP_WEIGHT * len(mine)
            if best is None or score < best[0]:
                reasons = [f"On call in {s['vehiclename']}" if s["oncall"] else f"On shift in {s['vehiclename']}"]
                if empty is not None:
                    reasons.append(f"{empty} mi from {'the last drop-off' if last else 'where the vehicle is' if s['vehicleid'] in spots else 'the base'}")
                reasons.append(f"{len(mine) + 1} trip{'s' if mine else ''} today")
                best = (score, s, reasons)
        item = {"legid": leg["legid"], "externalid": leg["externalid"], "passenger": leg["passenger"],
                "pickupat": leg["pickupat"], "driverid": None, "vehicleid": None,
                "drivername": None, "vehiclename": None, "reasons": [], "blocked": [],
                "priority": priority_of(leg), "confirmedat": leg["confirmedat"],
                "broker": bool(leg["brokerid"]), "gaveway": False}
        if best:
            _, s, reasons = best
            item.update(driverid=s["driverid"], vehicleid=s["vehicleid"], drivername=s["drivername"],
                        vehiclename=s["vehiclename"], reasons=reasons)
            held.setdefault(s["driverid"], []).append(leg)
        else:
            item["blocked"] = why_not or ["Nobody is on shift for the whole trip"]
            item["gaveway"] = bool(gave)
        out.append(item)
    # Placed by importance, not by time: each driver's count is said once the whole day is planned.
    for item in out:
        if item["driverid"]:
            n = len(held[item["driverid"]])
            item["reasons"][-1] = f"{n} trip{'s' if n > 1 else ''} today"
    return sorted(out, key=lambda i: i["pickupat"])


def availability(conn: Connection, accountid: str, legid: str) -> list[str]:
    """Whether anybody can take this leg, as it is about to be booked or changed: why not, or
    [] if it can be taken. Asked on every booking and every change, and a leg nobody can take is
    not booked or changed at all.

    On the day, once drivers are in the vehicles, somebody must hold one across the whole trip (an
    on-call one only after closing) and be clear to take it in that vehicle - qualified, the vehicle
    fitting the service, not on another trip then or too far from it to get there. Before that -
    next week's work, booked today - every hired driver not out then, and the vehicles in service: enough of them for this trip and every trip
    already booked then. A will-call has no time to ask about: its return plan answers for it."""
    from app.db import row
    leg = row(conn, f"""
        SELECT l.recordid AS legid, l.pickupat, l.dropoffat, l.appointmentat, l.pickuplat, l.pickuplng,
               l.dropofflat, l.dropofflng, {RANKED}
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid {PAYER}
        WHERE l.recordid = :l AND l.accountid = :a
    """, l=legid, a=accountid)
    if not leg or not leg["pickupat"]:
        return []
    day = leg["pickupat"].date()
    at = f"{leg['pickupat']:%-I:%M %p}"
    shifts = rows(conn, """
        SELECT s.driverid, s.vehicleid, s.startsat, s.endsat, s.oncall, v.externalid AS vehiclename,
               TRIM(CONCAT(d.firstname, ' ', d.lastname)) AS drivername
        FROM dayshifts s JOIN drivers d ON d.recordid = s.driverid
        JOIN vehicles v ON v.recordid = s.vehicleid
        WHERE s.accountid = :a AND s.workday = :w
    """, a=accountid, w=day)
    if not shifts:
        # Picked up inside the company's hours, or with somebody on call then.
        from app.routers.shifts import company_hours
        h = company_hours(conn, accountid, day)
        if h:
            opens, closes = plan.span(day, h["open"], h["close"]) if not h.get("closed") else (None, None)
            if not (opens and opens <= leg["pickupat"] < closes):
                covered = any(a <= leg["pickupat"] < b for a, b in
                              (plan.span(day, o["startsat"], o["endsat"]) for o in plan.on_call(conn, accountid, day)))
                if not covered:
                    if opens is None:
                        return [f"You are closed on {day:%A}s and nobody is on call that day. Put somebody on the "
                                f"On Call List for {day:%m/%d}, or book it for another day."]
                    if leg["pickupat"] < opens:
                        return [f"The {at} pickup is before you open at {opens:%-I:%M %p}."]
                    return [f"The {at} pickup is after your {closes:%-I:%M %p} closing and nobody is on call that "
                            f"evening. Put somebody on the On Call List for {day:%m/%d}, or book it for another time."]
        # Nobody put in a vehicle yet: every hired driver not out then, and the fleet in service.
        # Out is only a warning on an assignment (the dispatcher may know better on the day), but it
        # is not capacity to book against.
        away = dispatch._unavailable(conn, accountid, leg["pickupat"])["drivers"]
        crew = [d for d in plan.working(conn, accountid, day) if d not in away]
        if not crew:
            return [f"Every driver is out at {at}." if away else "There is no hired driver to take it."]
        said = dispatch.for_leg(conn, accountid, legid, only=set(crew))
        drivers = [d for d in said.get("drivers", []) if not d["blocked"]]
        vehicles = [v for v in said.get("vehicles", []) if not v["blocked"]]
        if drivers and vehicles:
            return _crowded(conn, accountid, leg, _ends(leg), {d["driverid"] for d in drivers},
                                    fleet={v["vehicleid"] for v in vehicles})
        if not drivers:
            return [f"No driver can take the {at} pickup."] + [
                f"{d['name'].title()}: {d['blocked'][0]}" for d in said.get("drivers", [])[:4]]
        return [f"No vehicle can carry the {at} pickup."] + [
            f"{v['name']}: {v['blocked'][0]}" for v in said.get("vehicles", [])[:4]]
    shifts += plan.on_call(conn, accountid, day)
    from app.routers.shifts import company_hours
    h = company_hours(conn, accountid, day)
    closes = plan.span(day, h["open"], h["close"])[1] if h and not h.get("closed") else None
    end = _ends(leg)
    on = []
    for s in shifts:
        s["from"], s["to"] = plan.span(day, s["startsat"], s["endsat"])
        if s["from"] <= leg["pickupat"] and end <= s["to"] and (
                not s["oncall"] or closes is None or leg["pickupat"] >= closes):
            on.append(s)
    if not on:
        return [f"Nobody is in a vehicle from {at} to {end:%-I:%M %p}, when this trip would end."]
    said = dispatch.for_leg(conn, accountid, legid, only={s["driverid"] for s in on},
                            vehicle_of={s["driverid"]: s["vehicleid"] for s in on})
    drivers = {d["driverid"]: d for d in said.get("drivers", [])}
    vehicles = {v["vehicleid"]: v for v in said.get("vehicles", [])}
    why, clear = [], set()
    for s in on:
        d, v = drivers.get(s["driverid"]), vehicles.get(s["vehicleid"])
        if d and not d["blocked"] and v and not v["blocked"]:
            clear.add(s["driverid"])
            continue
        reason = (d or {}).get("blocked") or [f"{s['vehiclename']} - {((v or {}).get('blocked') or ['not found'])[0]}"]
        why.append(f"{s['drivername'].title()}: {reason[0]}")
    if clear:
        return _crowded(conn, accountid, leg, end, clear,
                                vehicle_of={s["driverid"]: s["vehicleid"] for s in shifts})
    return [f"No driver on duty can take the {at} pickup."] + why[:4]


def _crowded(conn: Connection, accountid: str, leg: dict, end: datetime, clear: set[str],
             vehicle_of: dict | None = None, fleet: set[str] | None = None) -> list[str]:
    """Whether the drivers who can take this leg are already spoken for by trips booked at the same
    time and still waiting for a driver. At each moment of this trip, it and every waiting trip
    running then need a driver of their own, each from the drivers who could take it (a wheelchair
    trip only the lift's driver); if no way of sharing them out covers them all, this one cannot be
    taken. [] if it can. Every waiting trip counts - a confirmed trip keeps its place, whoever pays -
    except against a critical trip, which only another critical trip stands in front of. A driver
    on one also needs the time to drive between it and this one."""
    waiting = []
    for w in rows(conn, f"""
        SELECT l.recordid AS legid, l.pickupat, l.dropoffat, l.appointmentat, l.pickuplat, l.pickuplng,
               l.dropofflat, l.dropofflng, t.externalid, {RANKED}
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid {PAYER}
        WHERE l.accountid = :a AND l.recordid <> :l AND l.driverid IS NULL AND l.pickupat IS NOT NULL
          AND l.pickupat < :end AND l.pickupat >= :early AND l.outcomestate IS NULL
          AND l.executionstate = 'scheduled' AND t.deleted IS NULL AND t.cancelledon IS NULL
          AND t.brokerstate NOT IN ('offered', 'returnpending', 'returned') AND l.brokerstate IS NULL
    """, a=accountid, l=leg["legid"], end=end + dispatch.REACH, early=leg["pickupat"] - timedelta(hours=6)):
        if leg.get("critical") and not w.get("critical"):
            continue
        # Held from the drive to it (from this trip's drop-off) to the drive from it (to this pickup).
        w["from"] = w["pickupat"] - timedelta(minutes=dispatch.drive_minutes(
            _place(leg["dropofflat"], leg["dropofflng"]), _place(w["pickuplat"], w["pickuplng"])))
        w["end"] = _ends(w) + timedelta(minutes=dispatch.drive_minutes(
            _place(w["dropofflat"], w["dropofflng"]), _place(leg["pickuplat"], leg["pickuplng"])))
        if w["end"] > leg["pickupat"] and w["from"] < end:
            waiting.append(w)
    if not waiting:
        return []
    # Who could take each waiting trip, as it would be asked of that trip.
    for w in waiting:
        said = dispatch.for_leg(conn, accountid, w["legid"], only=set(vehicle_of) if vehicle_of else None,
                                vehicle_of=vehicle_of)
        fits = {v["vehicleid"] for v in said.get("vehicles", []) if not v["blocked"]}
        w["can"] = {d["driverid"] for d in said.get("drivers", []) if not d["blocked"]
                    and (not vehicle_of or vehicle_of.get(d["driverid"]) in fits)}
        # And, with nobody in a vehicle yet, the vehicles that could carry it: an ambulatory trip
        # does not need the lift a wheelchair trip does, so it does not use one up.
        w["fits"] = fits

    def covered(need: list[set[str]]) -> bool:
        """Whether each of these can have a driver of its own from its set (augmenting paths)."""
        held: dict[str, int] = {}

        def place(i: int, seen: set[str]) -> bool:
            for d in need[i]:
                if d not in seen:
                    seen.add(d)
                    if d not in held or place(held[d], seen):
                        held[d] = i
                        return True
            return False
        return all(place(i, set()) for i in range(len(need)))

    for t in [leg["pickupat"]] + [w["from"] for w in waiting if leg["pickupat"] < w["from"] < end]:
        now = [w for w in waiting if w["from"] <= t < w["end"]]
        drivers_ok = covered([clear] + [w["can"] for w in now])
        if drivers_ok and (fleet is None or covered([fleet] + [w["fits"] for w in now])):
            continue
        if drivers_ok:
            # Drivers enough; what runs out is the vehicles that can carry it.
            rivals = [w for w in now if w["fits"] & fleet] or now
            refs = ", ".join(w["externalid"] for w in rivals[:4]) + (" and more" if len(rivals) > 4 else "")
            many, n = len(fleet), len(rivals)
            return [f"{many} vehicle{'s' if many != 1 else ''} can carry the {leg['pickupat']:%-I:%M %p} pickup, "
                    f"and {n} trip{'s' if n != 1 else ''} already booked then {'needs' if n == 1 else 'need'} "
                    f"{'it' if many == 1 else 'them'}: {refs}. Assign those first, or book this for another time."]
        # Named: the waiting trips that can only have the drivers this one needs - not one another
        # driver could take as well.
        rivals = ([w for w in now if w["can"] and w["can"] <= clear]
                  or [w for w in now if w["can"] & clear] or now)
        refs = ", ".join(w["externalid"] for w in rivals[:4]) + (" and more" if len(rivals) > 4 else "")
        free, n = len(clear), len(rivals)
        return [f"{free} driver{'s' if free != 1 else ''} can take the {leg['pickupat']:%-I:%M %p} pickup, "
                f"and {n} trip{'s' if n != 1 else ''} already booked then {'needs' if n == 1 else 'need'} "
                f"{'that driver' if free == 1 else 'them'}: {refs}. Assign those first, or book this for another time."]
    return []


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
