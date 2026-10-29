"""The Shifts page: the day's driver-vehicle pairings, entered by hand or generated.

Every pairing that is saved passes app/shifts.fit - the compliance gate - and app/shifts.clash - one
shift per driver, one vehicle per shift at a time - here, on the server, whatever the screen offered.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import dispatch
from app import shifts as plan
from app import tripcheck
from app.activity import log
from app.db import engine, get_conn, newid, row, rows, run, saved, utcnow
from app.security import client_ip, current_user, editor

router = APIRouter(prefix="/api", tags=["shifts"])


def _clock(t) -> str:
    return plan.as_time(t).strftime("%H:%M")


@router.get("/shifts")
def the_day(day: date, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """One day: its shifts, every trip leg each driver already has, the company's hours that day,
    and the drivers and vehicles that could be put on a shift."""
    acct = user["accountid"]
    held = rows(conn, """
        SELECT s.recordid, s.driverid, s.vehicleid, s.startsat, s.endsat, s.source, s.reasons,
               TRIM(CONCAT(d.firstname, ' ', d.lastname)) AS drivername, v.externalid AS vehiclename,
               TRIM(CONCAT(COALESCE(v.make, ''), ' ', COALESCE(v.model, ''))) AS vehicledescr
        FROM dayshifts s JOIN drivers d ON d.recordid = s.driverid
        JOIN vehicles v ON v.recordid = s.vehicleid
        WHERE s.accountid = :a AND s.workday = :w
        ORDER BY d.lastname, d.firstname
    """, a=acct, w=day)
    for s in held:
        s["startsat"], s["endsat"] = _clock(s["startsat"]), _clock(s["endsat"])
        s["reasons"] = json.loads(s["reasons"]) if s["reasons"] else []
    legs = rows(conn, """
        SELECT l.recordid AS legid, l.driverid, l.pickupat, l.dropoffat, l.executionstate,
               l.outcomestate, t.externalid, t.passenger, v.externalid AS vehiclename
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        LEFT JOIN vehicles v ON v.recordid = l.vehicleid
        WHERE l.accountid = :a AND l.driverid IS NOT NULL AND DATE(l.pickupat) = :w
        ORDER BY l.pickupat
    """, a=acct, w=day)
    drivers = rows(conn, """
        SELECT recordid AS driverid, TRIM(CONCAT(firstname, ' ', lastname)) AS name
        FROM drivers WHERE accountid = :a AND deleted IS NULL AND stub = 0 AND status = 'hired'
        ORDER BY lastname, firstname
    """, a=acct)
    vehicles = rows(conn, """
        SELECT recordid AS vehicleid, externalid AS name FROM vehicles
        WHERE accountid = :a AND deleted IS NULL AND stub = 0 ORDER BY externalid
    """, a=acct)
    # When each driver's phone last said where they were (UTC), for the GPS line under their name.
    gps = {d: str(w["when"]) for d, w in dispatch._last_seen(conn, acct).items()}
    return {"day": day, "shifts": held, "legs": legs, "drivers": drivers, "vehicles": vehicles,
            "hours": company_hours(conn, acct, day), "gps": gps}


def company_hours(conn: Connection, acct: str, day: date) -> dict | None:
    """The company's hours that weekday (Company page, Hours Of Operation): {"open", "close"},
    {"closed": True}, or None when they have not been set."""
    raw = (row(conn, "SELECT hours FROM accounts WHERE recordid = :a", a=acct) or {}).get("hours")
    try:
        hours = (json.loads(raw) if raw else {}).get(str(day.weekday()), "unset")
    except ValueError:
        hours = "unset"
    return None if hours == "unset" else hours or {"closed": True}


class DayIn(BaseModel):
    day: date


@router.post("/shifts/eligible")
def eligible(body: DayIn, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """The hired drivers with at least one vehicle they may lawfully take that day - the only ones
    auto generation offers. Asked for when it opens, not with the day: every driver against every
    vehicle is the slow part."""
    acct = user["accountid"]
    hours = company_hours(conn, acct, body.day)
    opens = plan.as_time(hours["open"]) if hours and hours.get("open") else plan.DEFAULT_START
    noon = datetime.combine(body.day, plan.DEFAULT_START)
    # What stops a vehicle stops it for everybody, so each vehicle is judged once on its own, and
    # the drivers only against the vehicles left.
    usable = [v["recordid"] for v in rows(conn, """
        SELECT recordid FROM vehicles WHERE accountid = :a AND deleted IS NULL AND stub = 0
    """, a=acct) if not any(b.get("enforceable")
                            for b in tripcheck.vehicle_blockers(conn, acct, v["recordid"], None, noon))]
    hired = [d["recordid"] for d in rows(conn, """
        SELECT recordid FROM drivers WHERE accountid = :a AND deleted IS NULL AND stub = 0 AND status = 'hired'
    """, a=acct)]

    def cleared(driverid: str) -> bool:
        at = datetime.combine(body.day, opens)
        with engine.connect() as own:   # one connection per worker
            return any(plan.fit(own, acct, driverid, v, at, vehicle=False)["ok"] for v in usable)

    with ThreadPoolExecutor(max_workers=4) as pool:
        out = [d for d, ok in zip(hired, pool.map(cleared, hired)) if ok]
    return {"drivers": out}


class FitIn(BaseModel):
    day: date
    driverid: str
    startsat: str | None = None


@router.post("/shifts/fit")
def which_vehicles(body: FitIn, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Every vehicle, and whether this driver may take it that day - with the reasons where not."""
    acct = user["accountid"]
    at = datetime.combine(body.day, plan.as_time(body.startsat or plan.DEFAULT_START))
    out = []
    for v in rows(conn, """
        SELECT recordid AS vehicleid, externalid,
               TRIM(CONCAT(COALESCE(make, ''), ' ', COALESCE(model, ''))) AS descr
        FROM vehicles WHERE accountid = :a AND deleted IS NULL AND stub = 0 ORDER BY externalid
    """, a=acct):
        got = plan.fit(conn, acct, body.driverid, v["vehicleid"], at)
        out.append({"vehicleid": v["vehicleid"],
                    "name": f'{v["externalid"]} · {v["descr"]}'.strip(" ·"),
                    "available": got["ok"], "blocked": got["refused"], "drafts": got["said"],
                    "because": ["Cleared for this driver"] if got["ok"] else [], "warnings": []})
    out.sort(key=lambda x: (not x["available"], x["name"]))
    return {"vehicles": out}


class ShiftIn(BaseModel):
    day: date
    driverid: str
    vehicleid: str
    startsat: str
    endsat: str
    source: str = "manual"
    reasons: list[str] | None = None
    # Switching vehicles mid-shift: the driver's shift running at this one's start ends there.
    switch: bool = False


def _checked(conn: Connection, acct: str, body: ShiftIn, leaving: str | None = None) -> None:
    """The gate every saved shift passes: the pairing is lawful, and nothing collides."""
    try:
        plan.as_time(body.startsat), plan.as_time(body.endsat)
    except (ValueError, IndexError):
        raise HTTPException(400, "Give the start and end times") from None
    if plan.as_time(body.startsat) == plan.as_time(body.endsat):
        raise HTTPException(400, "The shift has to end at a different time from when it starts")
    # Within the company's hours that day, where they have been set.
    hours = company_hours(conn, acct, body.day)
    if hours and hours.get("closed"):
        raise HTTPException(409, f"The company is closed on {body.day:%A}s (Company, Hours Of Operation).")
    if hours:
        opens, closes = plan.span(body.day, hours["open"], hours["close"])
        starts, ends = plan.span(body.day, body.startsat, body.endsat)
        if starts < opens or ends > closes:
            raise HTTPException(409, f"{body.day:%A} hours are {opens:%-I:%M %p} to {closes:%-I:%M %p}. "
                                     f"The assignment has to fall within them.")
    at = datetime.combine(body.day, plan.as_time(body.startsat))
    got = plan.fit(conn, acct, body.driverid, body.vehicleid, at)
    if not got["ok"]:
        who = row(conn, "SELECT TRIM(CONCAT(firstname, ' ', lastname)) AS n FROM drivers WHERE recordid = :d",
                  d=body.driverid)
        unit = row(conn, "SELECT externalid FROM vehicles WHERE recordid = :v AND accountid = :a",
                   v=body.vehicleid, a=acct)
        raise HTTPException(409, f"{(who or {}).get('n', 'This driver').title()} may not take "
                                 f"{(unit or {}).get('externalid', 'this vehicle')}: {got['refused'][0]}")
    said = plan.clash(conn, acct, body.day, body.driverid, body.vehicleid, body.startsat,
                      body.endsat, leaving)
    if said:
        raise HTTPException(409, said)


def _switch(conn: Connection, acct: str, body: ShiftIn) -> None:
    """The driver changes vehicles at this shift's start: their shift running at that moment ends
    there, freeing its vehicle for the rest of the day."""
    begin = datetime.combine(body.day, plan.as_time(body.startsat))
    for s in rows(conn, """
        SELECT recordid, startsat, endsat FROM dayshifts
        WHERE accountid = :a AND workday = :w AND driverid = :d
    """, a=acct, w=body.day, d=body.driverid):
        a, b = plan.span(body.day, s["startsat"], s["endsat"])
        if a < begin < b:
            run(conn, "UPDATE dayshifts SET endsat = :e, updated = :now WHERE recordid = :s",
                e=plan.as_time(body.startsat), now=utcnow(), s=s["recordid"])


@router.post("/shifts")
def add_shift(body: ShiftIn, request: Request, user: dict = Depends(editor),
              conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    if body.switch:
        _switch(conn, acct, body)
    _checked(conn, acct, body)
    sid = newid()
    run(conn, """
        INSERT INTO dayshifts (recordid, accountid, workday, driverid, vehicleid, startsat, endsat,
                               source, reasons, added, addedby)
        VALUES (:id, :a, :w, :d, :v, :s, :e, :src, :r, :now, :by)
    """, id=sid, a=acct, w=body.day, d=body.driverid, v=body.vehicleid,
        s=plan.as_time(body.startsat), e=plan.as_time(body.endsat),
        src="auto" if body.source == "auto" else "manual",
        r=json.dumps(body.reasons) if body.reasons else None, now=utcnow(), by=user["recordid"])
    log(conn, user, "shift-added", "driver", body.driverid,
        {"day": str(body.day), "vehicleid": body.vehicleid, "startsat": body.startsat,
         "endsat": body.endsat, "source": body.source}, ip=client_ip(request))
    saved(conn)
    return {"recordid": sid}


@router.put("/shifts/{shiftid}")
def change_shift(shiftid: str, body: ShiftIn, request: Request, user: dict = Depends(editor),
                 conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    if not row(conn, "SELECT 1 AS x FROM dayshifts WHERE recordid = :s AND accountid = :a", s=shiftid, a=acct):
        raise HTTPException(404, "No such shift")
    _checked(conn, acct, body, leaving=shiftid)
    run(conn, """
        UPDATE dayshifts SET workday = :w, driverid = :d, vehicleid = :v, startsat = :s, endsat = :e,
                             source = 'manual', reasons = NULL, updated = :now
        WHERE recordid = :id AND accountid = :a
    """, w=body.day, d=body.driverid, v=body.vehicleid, s=plan.as_time(body.startsat),
        e=plan.as_time(body.endsat), now=utcnow(), id=shiftid, a=acct)
    log(conn, user, "shift-changed", "driver", body.driverid,
        {"day": str(body.day), "vehicleid": body.vehicleid, "startsat": body.startsat,
         "endsat": body.endsat}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.delete("/shifts/{shiftid}")
def remove_shift(shiftid: str, request: Request, user: dict = Depends(editor),
                 conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    held = row(conn, "SELECT driverid, workday FROM dayshifts WHERE recordid = :s AND accountid = :a",
               s=shiftid, a=acct)
    if not held:
        raise HTTPException(404, "No such shift")
    run(conn, "DELETE FROM dayshifts WHERE recordid = :s AND accountid = :a", s=shiftid, a=acct)
    log(conn, user, "shift-removed", "driver", held["driverid"], {"day": str(held["workday"])},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class WantedIn(BaseModel):
    driverid: str
    startsat: str | None = None
    endsat: str | None = None


class GenerateIn(BaseModel):
    day: date
    drivers: list[WantedIn]


@router.post("/shifts/generate")
def propose(body: GenerateIn, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """A vehicle for each of the day's drivers, with the reasons. Nothing is saved."""
    if not body.drivers:
        raise HTTPException(400, "Choose the drivers working that day")
    return {"proposal": plan.generate(conn, user["accountid"], body.day,
                                      [d.model_dump() for d in body.drivers])}


class PlanIn(BaseModel):
    day: date
    shifts: list[ShiftIn]


@router.post("/shifts/plan")
def save_plan(body: PlanIn, request: Request, user: dict = Depends(editor),
              conn: Connection = Depends(get_conn)):
    """Save a generated day. Each driver in it has their shift for the day replaced; every pairing
    passes the same gate as one entered by hand, and if one fails nothing is saved."""
    acct = user["accountid"]
    for s in body.shifts:
        run(conn, "DELETE FROM dayshifts WHERE accountid = :a AND workday = :w AND driverid = :d",
            a=acct, w=body.day, d=s.driverid)
    for s in body.shifts:
        s.day = body.day
        _checked(conn, acct, s)
        run(conn, """
            INSERT INTO dayshifts (recordid, accountid, workday, driverid, vehicleid, startsat, endsat,
                                   source, reasons, added, addedby)
            VALUES (:id, :a, :w, :d, :v, :s, :e, 'auto', :r, :now, :by)
        """, id=newid(), a=acct, w=body.day, d=s.driverid, v=s.vehicleid,
            s=plan.as_time(s.startsat), e=plan.as_time(s.endsat),
            r=json.dumps(s.reasons) if s.reasons else None, now=utcnow(), by=user["recordid"])
    log(conn, user, "shifts-generated", None, None,
        {"day": str(body.day), "shifts": len(body.shifts)}, ip=client_ip(request))
    saved(conn)
    return {"ok": True, "saved": len(body.shifts)}
