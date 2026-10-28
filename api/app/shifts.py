"""The day's shifts: which vehicle each working driver takes, and over what hours.

A shift is a pairing, and a pairing is only ever one the compliance rules allow. The question asked
is the one the trip check asks about a driver in a vehicle, without a trip: is the driver hired and
not marked out, are they qualified for THIS vehicle - the vehicle decides what they are operating
(app/facts._on_this_vehicle), so a 15-passenger bus asks Part 391 of whoever drives it - and may the
vehicle itself go out. A payer program's own rules are not asked: a shift is not for any one payer,
and each trip still answers to its own program when it is assigned.

Auto generation pairs the day's drivers with the fleet. Compliance first, always; then, among the
vehicles a driver may take, the best fit - their usual vehicle, the one nearest them, the one with
the fewest miles on it this week. Drivers with the fewest choices choose first, so a driver who can
only take the lift van is not left without it because somebody who could take anything took it.
Nothing is saved by generating: the office reads the proposal, with the reasons, and saves it.
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy.engine import Connection

from app import dispatch, hos, rules, tripcheck, wheremap
from app import facts as factset
from app.db import row, rows

DEFAULT_START, DEFAULT_END = time(8, 0), time(17, 0)


def as_time(v) -> time:
    """A TIME column as MariaDB hands it back (a timedelta) or as typed ("08:30"), as a time."""
    if isinstance(v, time):
        return v
    if isinstance(v, timedelta):
        secs = int(v.total_seconds()) % 86400
        return time(secs // 3600, secs % 3600 // 60)
    hh, mm = str(v)[:5].split(":")
    return time(int(hh), int(mm))


def span(day: date, start, end) -> tuple[datetime, datetime]:
    """A shift as two moments. An end at or before the start runs past midnight."""
    a = datetime.combine(day, as_time(start))
    b = datetime.combine(day, as_time(end))
    return a, (b if b > a else b + timedelta(days=1))


def fit(conn: Connection, accountid: str, driverid: str, vehicleid: str, at: datetime,
        vehicle: bool = True) -> dict:
    """Whether this driver may take this vehicle on this day, and if not, every reason why.

    Refused only for what may refuse a trip - a rule a reviewer approved or a structural fact; a
    shortfall under a rule still in draft is said, as it is everywhere else, and stops nothing."""
    refused, said = [], []
    d = row(conn, "SELECT status FROM drivers WHERE recordid = :d AND accountid = :a AND deleted IS NULL",
            d=driverid, a=accountid)
    if not d:
        return {"ok": False, "refused": ["No such driver on this account"], "said": []}
    if d["status"] != "hired":
        refused.append("Not hired")
    away = dispatch._unavailable(conn, accountid, at)
    if driverid in away["drivers"]:
        refused.append(away["drivers"][driverid])
    if vehicleid in away["vehicles"]:
        refused.append(away["vehicles"][vehicleid])
    if d["status"] == "hired":
        facts = factset.assemble(conn, accountid, driverid, vehicleid)["facts"]
        items = rules.for_driver(conn, accountid, driverid, facts, today=at.date())
        blockers, _w, _h = tripcheck.judge_items(items, None, at)
        for b in blockers:
            words = dispatch._because({"name": b.get("name"), "code": b["code"], "why": b.get("reason")})
            (refused if b.get("enforceable") else said).append(
                words if b.get("enforceable") else f"{words} (rule not yet approved)")
    # vehicle=False: the caller has judged the vehicle on its own already (see usable_vehicles).
    for b in tripcheck.vehicle_blockers(conn, accountid, vehicleid, None, at) if vehicle else []:
        words = dispatch._because({"name": b.get("name"), "code": b["code"], "why": b.get("reason")})
        (refused if b.get("enforceable") else said).append(
            words if b.get("enforceable") else f"{words} (rule not yet approved)")
    return {"ok": not refused, "refused": list(dict.fromkeys(refused)), "said": list(dict.fromkeys(said))}


def clash(conn: Connection, accountid: str, day: date, driverid: str, vehicleid: str, start, end,
          leaving: str | None = None) -> str | None:
    """What this shift would collide with on the day: another of this driver's shifts at hours that
    overlap - a driver may change vehicles during the day, not be in two at once - or the vehicle on
    somebody else's shift at hours that overlap. `leaving` is the shift being changed."""
    a, b = span(day, start, end)
    for s in rows(conn, """
        SELECT s.startsat, s.endsat, v.externalid FROM dayshifts s JOIN vehicles v ON v.recordid = s.vehicleid
        WHERE s.accountid = :a AND s.workday = :w AND s.driverid = :d AND (:x IS NULL OR s.recordid <> :x)
    """, a=accountid, w=day, d=driverid, x=leaving):
        c, e = span(day, s["startsat"], s["endsat"])
        if a < e and c < b:
            return (f"This driver is already on a shift in {s['externalid']} "
                    f"{c:%-I:%M %p} - {e:%-I:%M %p}.")
    for s in rows(conn, """
        SELECT s.startsat, s.endsat, TRIM(CONCAT(d.firstname, ' ', d.lastname)) AS who, v.externalid
        FROM dayshifts s JOIN drivers d ON d.recordid = s.driverid
        JOIN vehicles v ON v.recordid = s.vehicleid
        WHERE s.accountid = :a AND s.workday = :w AND s.vehicleid = :v
          AND (:x IS NULL OR s.recordid <> :x)
    """, a=accountid, w=day, v=vehicleid, x=leaving):
        c, e = span(day, s["startsat"], s["endsat"])
        if a < e and c < b:
            return (f"{s['externalid']} is on {s['who'].title()}'s shift "
                    f"{c:%-I:%M %p} - {e:%-I:%M %p}.")
    return None


def roster(conn: Connection, accountid: str, day: date) -> dict[str, tuple[time, time]]:
    """Who usually works this weekday, and their usual hours - the weekly hours on their record."""
    out = {}
    for s in rows(conn, """
        SELECT driverid, startsat, endsat FROM drivershifts
        WHERE accountid = :a AND weekday = :wd
          AND (effectivefrom IS NULL OR effectivefrom <= :on)
          AND (effectiveto IS NULL OR effectiveto >= :on)
        ORDER BY startsat
    """, a=accountid, wd=day.weekday(), on=day):
        out.setdefault(s["driverid"], (as_time(s["startsat"]), as_time(s["endsat"])))
    return out


def _usual(conn: Connection, accountid: str) -> dict[str, str]:
    """The vehicle each driver drove most recently - on a shift, or on a trip."""
    out = {}
    for r in rows(conn, """
        SELECT driverid, vehicleid FROM (
            SELECT driverid, vehicleid, workday AS at FROM dayshifts WHERE accountid = :a
            UNION ALL
            SELECT driverid, vehicleid, DATE(assignedon) AS at FROM tripassignments
             WHERE accountid = :a AND vehicleid IS NOT NULL AND driverid IS NOT NULL
        ) x ORDER BY at
    """, a=accountid):
        out[r["driverid"]] = r["vehicleid"]
    return out


def _vehicle_spots(conn: Connection, accountid: str) -> dict[str, tuple[float, float]]:
    """Where each vehicle was last seen: the newest position reported from it."""
    out = {}
    for r in rows(conn, """
        SELECT l.vehicleid, l.latitude, l.longitude FROM driverlocations l
        JOIN (SELECT vehicleid, MAX(recordedon) AS newest FROM driverlocations
              WHERE accountid = :a AND vehicleid IS NOT NULL GROUP BY vehicleid) n
          ON n.vehicleid = l.vehicleid AND n.newest = l.recordedon
        WHERE l.accountid = :a
    """, a=accountid):
        out[r["vehicleid"]] = (float(r["latitude"]), float(r["longitude"]))
    return out


def _week_miles(conn: Connection, accountid: str, day: date) -> dict[str, float]:
    """Miles each vehicle has run in the seven days before this one."""
    return {r["vehicleid"]: float(r["miles"] or 0) for r in rows(conn, """
        SELECT vehicleid, SUM(miles) AS miles FROM triplegs
        WHERE accountid = :a AND vehicleid IS NOT NULL AND miles IS NOT NULL
          AND DATE(COALESCE(dropoffat, pickupat)) BETWEEN :f AND :t
        GROUP BY vehicleid
    """, a=accountid, f=day - timedelta(days=7), t=day - timedelta(days=1))}


def generate(conn: Connection, accountid: str, day: date, wanted: list[dict]) -> list[dict]:
    """A vehicle for each of the day's drivers, with the reasons. Saves nothing.

    `wanted` is [{driverid, startsat, endsat}]. A driver no vehicle can lawfully be given to is
    returned without one, and with what stands in the way."""
    vehicles = rows(conn, """
        SELECT recordid, externalid FROM vehicles
        WHERE accountid = :a AND deleted IS NULL AND stub = 0 ORDER BY externalid
    """, a=accountid)
    usual = _usual(conn, accountid)
    seen = dispatch._last_seen(conn, accountid)
    spots = _vehicle_spots(conn, accountid)
    base = wheremap.base_of(conn, accountid) or {}
    home = ((float(base["latitude"]), float(base["longitude"]))
            if base.get("latitude") is not None else None)
    miles = _week_miles(conn, accountid, day)
    # Vehicles already on a shift that day and not being re-planned here keep their hours.
    planning = {w["driverid"] for w in wanted}
    held = [h for h in rows(conn, """
        SELECT driverid, vehicleid, startsat, endsat FROM dayshifts WHERE accountid = :a AND workday = :w
    """, a=accountid, w=day) if h["driverid"] not in planning]

    options = {}
    for w in wanted:
        at = datetime.combine(day, as_time(w.get("startsat") or DEFAULT_START))
        options[w["driverid"]] = {}
        for v in vehicles:
            got = fit(conn, accountid, w["driverid"], v["recordid"], at)
            options[w["driverid"]][v["recordid"]] = got

    def score(driverid: str, vehicleid: str) -> tuple[float, list[str]]:
        said, s = [], 0.0
        if usual.get(driverid) == vehicleid:
            s -= 1000
            said.append("Usual vehicle")
        here = seen.get(driverid)
        there = spots.get(vehicleid) or home
        if here and there:
            far = round(dispatch._miles((here["lat"], here["lng"]), there), 1)
            s += far
            said.append(f"{far} mi from it")
        run = miles.get(vehicleid, 0.0)
        s += run / 50
        said.append(f"{round(run)} mi this week")
        return s, said

    taken: list[tuple[str, datetime, datetime]] = [
        (h["vehicleid"], *span(day, h["startsat"], h["endsat"])) for h in held]
    out = []
    # The driver with the fewest vehicles open to them chooses first.
    order = sorted(wanted, key=lambda w: sum(1 for o in options[w["driverid"]].values() if o["ok"]))
    for w in order:
        start, end = as_time(w.get("startsat") or DEFAULT_START), as_time(w.get("endsat") or DEFAULT_END)
        a, b = span(day, start, end)
        free = [vid for vid, o in options[w["driverid"]].items() if o["ok"]
                and not any(t[0] == vid and a < t[2] and t[1] < b for t in taken)]
        name = row(conn, "SELECT TRIM(CONCAT(firstname, ' ', lastname)) AS n FROM drivers WHERE recordid = :d",
                   d=w["driverid"])["n"]
        standing = hos.standing(conn, accountid, w["driverid"], day)
        hours = hos.hours(standing["weektotal"]) if standing else None
        if not free:
            # Why there is none, in the terms that are true for this driver: every vehicle they may
            # take has gone to somebody else; or something about the DRIVER stops them in any
            # vehicle (what every refusal has in common); or, failing both, each vehicle's own reason.
            unit_of = {v["recordid"]: v["externalid"] for v in vehicles}
            mine = options[w["driverid"]]
            lawful = [vid for vid, o in mine.items() if o["ok"]]
            if lawful:
                blocked = ["Every vehicle they may take is on another shift: "
                           + ", ".join(unit_of[v] for v in lawful)]
            else:
                common = set.intersection(*(set(o["refused"]) for o in mine.values())) if mine else set()
                blocked = (sorted(common) if common else
                           [f"{unit_of[vid]}: {o['refused'][0]}" for vid, o in mine.items()])
            out.append({"driverid": w["driverid"], "drivername": name, "vehicleid": None,
                        "startsat": start.strftime("%H:%M"), "endsat": end.strftime("%H:%M"),
                        "reasons": [], "hours": hours,
                        "blocked": blocked or ["No vehicle is on file"]})
            continue
        best = min(free, key=lambda vid: score(w["driverid"], vid)[0])
        taken.append((best, a, b))
        unit = next(v["externalid"] for v in vehicles if v["recordid"] == best)
        out.append({"driverid": w["driverid"], "drivername": name, "vehicleid": best,
                    "vehiclename": unit, "startsat": start.strftime("%H:%M"),
                    "endsat": end.strftime("%H:%M"), "reasons": score(w["driverid"], best)[1],
                    "hours": hours, "blocked": None})
    return sorted(out, key=lambda x: x["drivername"])
