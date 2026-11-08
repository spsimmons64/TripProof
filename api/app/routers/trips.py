###################################################################################################
# The trip ledger - imports, the trip list (the pre-billing scrub), trip detail, re-evaluation.
#
# PHI is never in a list response. Trip detail returns operational facts only; member identity and
# addresses come from a separate endpoint that logs the access (minimum necessary).
###################################################################################################
import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import dayplan, dispatch, importer, phi, routing, sms, tripcheck
from app import shifts as plan
from app.routers import driverapp
from app import rates as rateset
from app import wheremap
from app.activity import log
from app.db import get_conn, localnow, newid, row, rows, run, saved, utcnow
from app.evaluator import evaluate
from app.security import client_ip, current_user, editor

router = APIRouter(prefix="/api", tags=["trips"])


def _as_instant(local: datetime, tz: str) -> datetime:
    """A wall-clock time in the company's zone, as the UTC instant it names."""
    return local.replace(tzinfo=ZoneInfo(tz)).astimezone(timezone.utc).replace(tzinfo=None)


def _account_zone(conn: Connection, accountid: str) -> str:
    """The zone the company's wall clock runs on, for a user who has not set their own."""
    return (row(conn, "SELECT timezone FROM accounts WHERE recordid = :a", a=accountid)
            or {}).get("timezone") or "America/New_York"

MAX_UPLOAD = 50 * 1024 * 1024


# ------------------------------------------------------------------------------------------------
# Imports
# ------------------------------------------------------------------------------------------------

@router.get("/imports")
def list_imports(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    return rows(conn, """
        SELECT recordid, filename, status, rowcount, tripcount, added, decidedon
        FROM importbatches WHERE accountid = :a ORDER BY added DESC LIMIT 100
    """, a=user["accountid"])


@router.post("/imports")
async def stage_import(request: Request, file: UploadFile = File(...), mapping: str | None = Form(None),
                       user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File is larger than 50 MB")
    result = importer.stage(conn, user, file.filename or "upload.csv", data, json.loads(mapping) if mapping else None)
    log(conn, user, "import-stage", "importbatch", result["recordid"], {"filename": file.filename},
        phi=True, ip=client_ip(request))
    return result


@router.get("/imports/{batchid}")
def get_import(batchid: str, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    return importer.preview(conn, user, batchid)


@router.post("/imports/{batchid}/accept")
def accept_import(batchid: str, request: Request, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    result = importer.commit(conn, user, batchid)
    log(conn, user, "import-accept", "importbatch", batchid, result, phi=True, ip=client_ip(request))
    return result


@router.post("/imports/{batchid}/reject")
def reject_import(batchid: str, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    importer.reject(conn, user, batchid)
    log(conn, user, "import-reject", "importbatch", batchid)
    return {"ok": True}


# ------------------------------------------------------------------------------------------------
# Trips
# ------------------------------------------------------------------------------------------------

# What the trips grid may sort on, and what each one means in SQL. The trip number breaks every
# tie, so a page boundary never splits two rows that compare equal and shows one of them twice.
SORTS = {
    "externalid": "t.externalid {d}",
    "tripdate": "t.tripdate {d}",
    "broker": "b.code {d}",
    "drivers": "drivers {d}",
    "failures": "(e.tripid IS NOT NULL) {d}",
    "billingstatus": "t.billingstatus {d}",
    "billedamount": "t.billedamount {d}",
}


@router.get("/trips")
def list_trips(status: str = "all", billing: str | None = None, datefrom: str | None = None, dateto: str | None = None,
               q: str | None = None, driverid: str | None = None, vehicleid: str | None = None,
               sort: str = "tripdate", dir: str = "desc", page: int = 1, pagesize: int = 100,
               user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    pagesize = max(1, min(pagesize, 500))
    # A column may be sorted on only if it is named here. The grid sends a column id and this maps
    # it to SQL - never the other way round, because a sort taken from the query string and dropped
    # into an ORDER BY is somewhere a database gets asked questions nobody wrote.
    order = SORTS.get(sort, SORTS["tripdate"])
    order = order.replace("{d}", "DESC" if str(dir).lower() == "desc" else "ASC")
    where = ["t.accountid = :a", "t.deleted IS NULL"]
    params = {"a": user["accountid"]}
    if status == "fail":
        where.append("e.tripid IS NOT NULL")
    elif status == "pass":
        where.append("e.tripid IS NULL AND t.lastrunid IS NOT NULL")
    if billing:
        where.append("t.billingstatus = :billing")
        params["billing"] = billing
    if datefrom:
        where.append("t.tripdate >= :df")
        params["df"] = datefrom
    if dateto:
        where.append("t.tripdate <= :dt")
        params["dt"] = dateto
    if q:
        where.append("t.externalid LIKE CONCAT('%', :q, '%')")
        params["q"] = q
    if driverid:
        where.append("EXISTS (SELECT 1 FROM triplegs x WHERE x.tripid = t.recordid AND x.driverid = :did)")
        params["did"] = driverid
    if vehicleid:
        where.append("EXISTS (SELECT 1 FROM triplegs x WHERE x.tripid = t.recordid AND x.vehicleid = :vid)")
        params["vid"] = vehicleid
    clause = " AND ".join(where)
    total = row(conn, f"""
        SELECT COUNT(*) AS n, COALESCE(SUM(t.billedamount), 0) AS amount
        FROM trips t LEFT JOIN tripexposure e ON e.tripid = t.recordid WHERE {clause}
    """, **params)
    items = rows(conn, f"""
        SELECT t.recordid, t.externalid, t.tripdate, t.servicelevel, t.billedamount, t.billingstatus,
               b.code AS broker, e.failures,
               (SELECT GROUP_CONCAT(DISTINCT c.reason ORDER BY c.reason SEPARATOR ' | ')
                FROM legchecks c WHERE c.tripid = t.recordid AND c.runid = t.lastrunid AND c.outcome <> 'pass') AS reasons,
               (SELECT GROUP_CONCAT(DISTINCT CONCAT(d.firstname, ' ', d.lastname) SEPARATOR ', ')
                FROM triplegs l JOIN drivers d ON d.recordid = l.driverid WHERE l.tripid = t.recordid) AS drivers
        FROM trips t
        LEFT JOIN tripexposure e ON e.tripid = t.recordid
        LEFT JOIN payers b ON b.recordid = t.brokerid
        WHERE {clause}
        ORDER BY {order}, t.externalid
        LIMIT :lim OFFSET :off
    """, lim=pagesize, off=(max(page, 1) - 1) * pagesize, **params)
    return {"total": total["n"], "amount": total["amount"], "page": page, "pagesize": pagesize, "items": items}


class Leg(BaseModel):
    pickupat: datetime | None = None      # none on a will-call return: the passenger rings when ready
    appointmentat: datetime | None = None  # when the passenger is due at the drop-off
    dropoffat: datetime | None = None
    pickupplace: str
    dropoffplace: str
    driverid: str | None = None
    vehicleid: str | None = None
    readyabout: datetime | None = None    # a will-call return: when the passenger should be ready
    returnplan: str | None = None         # a will-call return that could run past closing: RETURN_PLANS
    responsibility: str | None = None     # a return: RESPONSIBILITY - who brings the passenger home
    responsibilitynote: str | None = None # the other provider, and their confirmation


class Booking(BaseModel):
    passenger: str
    passengerphone: str | None = None
    tripdate: date
    servicelevel: str = "ambulatory"
    payer: str = "private"
    brokerid: str | None = None
    brokertripno: str | None = None       # the broker's own number for the trip
    note: str | None = None
    critical: bool = False                # cannot be missed: placed first by Auto Assign
    legs: list[Leg]


@router.get("/trips/suggest")
def who_should_take_it(when: datetime, minutes: int = 60, service: str = "ambulatory",
                       seats: int = 1, pickup: str | None = None,
                       payerid: str | None = None, payer: str = "private",
                       pickupplace: str | None = None, dropoffplace: str | None = None,
                       user: dict = Depends(current_user),
                       conn: Connection = Depends(get_conn)):
    """Which driver and which vehicle suit a job, and the reasons for the order.

    `pickup` is "lat,lng" where the office has it; otherwise the pickup address is placed. Without
    either the ranking still works - it just cannot sort by who is nearest, and says so against
    each driver. With the payer and the addresses, every candidate is put to the trip check the
    assignment will go through: the payer's line and approvals, and the rules of both states."""
    at = None
    if pickup:
        try:
            lat, lng = (float(x) for x in pickup.split(",", 1))
            at = (lat, lng)
        except ValueError:
            raise HTTPException(400, "pickup must be lat,lng") from None
    elif pickupplace:
        at = wheremap.place(pickupplace)
    trip = None
    if pickupplace or dropoffplace or payerid:
        trip = {"vehicleid": None, "pickupat": when, "tripdate": when.date(), "brokerid": payerid,
                "payer": payer, "servicelevel": service, "pickupplace": pickupplace,
                "dropoffplace": dropoffplace, "originplace": pickupplace}
    return dispatch.best(conn, user["accountid"], when=when, minutes=minutes,
                         service=service, seats=seats, pickup=at, trip=trip)


# How a passenger gets home when their will-call return could run past closing. Setting a return
# time instead is the third answer, and it is not a plan to keep: the leg is then not a will-call.
RETURN_PLANS = {"oncall": "An on-call driver", "broker": "The broker arranges the return"}
PAST_CLOSING = timedelta(minutes=90)      # from here, a will-call still out needs its coverage recorded
FACILITY_WARNING = 60                     # minutes before a facility closes, with a passenger still waiting there
CALL_OVERDUE = 30                         # minutes past Ready About with no call before somebody rings them
# Who brings the passenger home. The broker taking it is a hand-back (brokerstate): until the
# broker confirms, the return is still ours - asking is not the same as it being taken.
RESPONSIBILITY = {"provider": "We bring them home", "broker": "Ask the broker to take it",
                  "other": "Another provider (confirmed)", "unconfirmed": "Not decided yet"}
# Where the word that a will-call passenger is ready came from.
ACTIVATION = {"passenger": "The passenger", "facility": "The facility", "brokerportal": "The broker's portal",
              "brokerphone": "The broker, by telephone", "driver": "The driver"}


def return_undecided(conn: Connection, acct: str, tripid: str) -> str | None:
    """A trip whose ride home nobody has decided on yet: the outbound is not given a driver until
    somebody has. Returns the passenger, or None."""
    held = row(conn, """
        SELECT t.passenger FROM triplegs l JOIN trips t ON t.recordid = l.tripid
        WHERE l.tripid = :t AND l.accountid = :a AND l.legnumber > 1 AND l.responsibility = 'unconfirmed'
          AND l.brokerstate IS NULL AND l.outcomestate IS NULL LIMIT 1
    """, t=tripid, a=acct)
    return held["passenger"] if held else None


def _undecided_said(passenger: str) -> str:
    return (f"Who brings {passenger} home has not been decided. Decide it (Edit Trip, Who Brings Them "
            f"Home) before the trip there is given a driver.")
# A trip's broker state when it is not ours to run: offered and not accepted, or on its way back.
# Ours otherwise - 'none' for our own, 'accepted' for a broker's - never empty.
HANDED_BACK = ("offered", "returnpending", "returned")
# A will-call's Ready About when nobody says: an hour after the appointment it is coming back from.
READY_AFTER = timedelta(minutes=60)


def _closes(conn: Connection, acct: str, day: date) -> datetime | None:
    """When the company's Transportation Hours end that day; None where none are set."""
    from app.routers.shifts import company_hours
    h = company_hours(conn, acct, day)
    if not h or h.get("closed"):
        return None
    return plan.span(day, h["open"], h["close"])[1]


def _doubt(conn: Connection, acct: str, legid: str) -> str:
    """Put first in a refusal: an address in doubt, which may be all that is wrong."""
    from app.routers.places import misplaced
    leg = row(conn, "SELECT pickupplace, dropoffplace FROM triplegs WHERE recordid = :l", l=legid) or {}
    said = [f"The {what} address {why} - check it." for what, where in (("pickup", leg.get("pickupplace")),
                                                                      ("drop-off", leg.get("dropoffplace")))
            if where and (why := misplaced(conn, acct, where))]
    return " ".join(said) + (" " if said else "")


def after_hours(conn: Connection, acct: str, day: date, ready: datetime, pickupplace: str,
                dropoffplace: str) -> dict:
    """Whether a will-call return ready about then could get the passenger home after closing:
    the estimate, not a promise - the drive is the one every trip is held for (leg_minutes)."""
    from app.routers.places import _where
    here, there = _where(conn, acct, pickupplace), _where(conn, acct, dropoffplace)
    home = ready + timedelta(minutes=dispatch.leg_minutes({
        "pickupat": ready, "pickuplat": here and here[0], "pickuplng": here and here[1],
        "dropofflat": there and there[0], "dropofflng": there and there[1]}))
    close = _closes(conn, acct, day)
    return {"ready": ready, "home": home, "close": close, "needsplan": bool(close and home > close)}


def _plan_said(day: date, got: dict) -> str:
    return (f"This return could run past closing: ready about {got['ready']:%-I:%M %p}, home about "
            f"{got['home']:%-I:%M %p}, and {day:%A} closes at {got['close']:%-I:%M %p}. "
            f"Choose how the passenger gets home.")


@router.get("/dispatch/return-check")
def return_check(day: date, ready: datetime, pickup: str, dropoff: str,
                 user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """For Book A Trip and Edit Trip, as the form is filled: does this will-call need a plan."""
    from app.routers.places import _clock, facility_closes
    got = after_hours(conn, user["accountid"], day, ready, pickup, dropoff)
    place = facility_closes(conn, user["accountid"], pickup)
    return {**got, "plans": RETURN_PLANS, "facility": place and place["name"],
            "facilitycloses": place and _clock(place["closesat"])}


def _hand_back_leg(conn: Connection, acct: str, user: dict, trip: dict, leg: dict, reason: str,
                   note: str | None) -> None:
    """One leg handed back to the broker - usually the ride home. Whoever was on it comes off and
    is told; it stays ours, on the board, until the broker confirms they have it."""
    if leg.get("driverid"):
        run(conn, """
            UPDATE tripassignments SET endedon = :now, endedby = :by, endreason = 'returned'
            WHERE accountid = :a AND legid = :l AND endedon IS NULL
        """, now=utcnow(), by=user["recordid"], a=acct, l=leg["recordid"])
        run(conn, "UPDATE triplegs SET driverid = NULL, vehicleid = NULL WHERE recordid = :l AND accountid = :a",
            l=leg["recordid"], a=acct)
        sms.tell(conn, acct, leg["driverid"], "removed",
                 f"Trip {trip['externalid']}, pickup {sms.when(leg['pickupat'])}, is no longer yours. Open the app.",
                 trip["recordid"], leg["recordid"])
    run(conn, """
        INSERT INTO triprejections (recordid, accountid, tripid, legid, reason, note, requestedon, requestedby)
        VALUES (:id, :a, :t, :l, :r, :n, :now, :by)
    """, id=newid(), a=acct, t=trip["recordid"], l=leg["recordid"], r=reason,
        n=(note or "").strip()[:600] or None, now=utcnow(), by=user["recordid"])
    run(conn, "UPDATE triplegs SET brokerstate = 'returnpending' WHERE recordid = :l AND accountid = :a",
        l=leg["recordid"], a=acct)


@router.post("/trips")
def book_a_trip(body: Booking, request: Request, user: dict = Depends(editor),
                conn: Connection = Depends(get_conn)):
    """Book a trip by hand - the private pay and telephone case.

    The imported trips arrive priced; this one does not. `billedamount` is zero until a fee
    schedule exists to work it out, and saying zero is honest where inventing a number is
    not."""
    got = book(conn, user, body)
    log(conn, user, "trip-booked", "trip", got["recordid"],
        {"passenger": body.passenger, "legs": len(body.legs)}, ip=client_ip(request))
    saved(conn)
    return got


def book(conn: Connection, user: dict, body: Booking) -> dict:
    """Every check and every row of a booking, without committing it. Also how a facility's trip
    request is tried (inside a savepoint that is then rolled back) and how it is booked once the
    office accepts it: one set of rules for every way a trip comes in."""
    acct = user["accountid"]
    if not body.legs:
        raise HTTPException(400, "A trip needs at least one leg")
    # Only a return can wait for the passenger to call. The outbound is booked for a time.
    if body.legs[0].pickupat is None:
        raise HTTPException(400, "Give the pickup time")
    if body.servicelevel not in dispatch.SERVICE:
        raise HTTPException(400, f"Unknown service level {body.servicelevel}")
    # A payer not carried for where the trip begins cannot be billed for it - refused here rather
    # than found when every driver comes back blocked.
    origin = tripcheck.pickup_state(body.legs[0].pickupplace)
    if body.brokerid and not tripcheck.contract_for(conn, acct, body.brokerid, body.tripdate, origin):
        raise HTTPException(400, tripcheck.no_line(conn, acct, body.brokerid, origin))
    # Priced before it is written, under the schedule in force for this payer on that day. The
    # figure is the base fare: nobody has driven anywhere yet, so mileage is added when they have.
    priced = rateset.quote(conn, acct, payerid=body.brokerid, servicelevel=body.servicelevel,
                           on=body.tripdate, legs=len(body.legs),
                           state=tripcheck.pickup_state(body.legs[0].pickupplace))
    # A will-call return that could get the passenger home after closing is booked with a plan for
    # it, or not at all: found now, not at six o'clock with the passenger waiting.
    for n, leg in enumerate(body.legs):
        if leg.pickupat is not None:
            continue
        if leg.returnplan and leg.returnplan not in RETURN_PLANS:
            raise HTTPException(400, "Unknown return plan")
        first = body.legs[0]
        leg.readyabout = leg.readyabout or ((first.appointmentat or first.pickupat) + READY_AFTER)
        got = after_hours(conn, acct, body.tripdate, leg.readyabout, leg.pickupplace, leg.dropoffplace)
        # Past closing it has to be decided, not assumed: who brings them home (we do - on call -
        # the broker, another provider), or not decided yet, said out loud.
        if got["needsplan"] and not leg.returnplan and not leg.responsibility:
            raise HTTPException(409, _plan_said(body.tripdate, got))
        if got["needsplan"] and leg.responsibility == "provider":
            leg.returnplan = "oncall"
    for n, leg in enumerate(body.legs):
        if n == 0:
            continue
        if leg.responsibility and leg.responsibility not in RESPONSIBILITY:
            raise HTTPException(400, "Unknown answer to who brings them home")
        if leg.returnplan == "broker":
            leg.responsibility = "broker"
        if leg.responsibility == "broker" and not body.brokerid:
            raise HTTPException(400, "Only a broker's trip can have the broker arrange the return.")
        if leg.responsibility == "other" and not (leg.responsibilitynote or "").strip():
            raise HTTPException(400, "Say which provider is bringing them home, and their confirmation.")
    tripid = newid()
    # Its own reference until a broker gives it one. Visibly local, so nobody mistakes it for
    # a broker's number when the two sit in one list.
    external = f"TP-{body.tripdate:%Y%m%d}-{tripid[:6].upper()}"
    run(conn, """
        INSERT INTO trips (recordid, accountid, externalid, tripdate, servicelevel, critical,
                           billedamount, billingstatus, scheduleid, brokerid, brokertripno, passenger,
                           passengerphone, payer, note, bookedby, added)
        VALUES (:id, :a, :x, :on, :svc, :crit, :amt, 'unbilled', :sched, :b, :btn, :p, :ph, :pay, :n, :by, :now)
    """, id=tripid, a=acct, x=external, on=body.tripdate, svc=body.servicelevel, crit=int(body.critical),
        btn=((body.brokertripno or "").strip().upper()[:40] or None) if body.brokerid else None,
        amt=priced["amount"] or 0, sched=priced["scheduleid"], b=body.brokerid, p=body.passenger.strip()[:160],
        ph=(body.passengerphone or "").strip()[:32] or None, pay=body.payer[:16],
        n=(body.note or "").strip()[:512] or None, by=user["recordid"], now=utcnow())

    if any(leg.pickupat is None and (leg.driverid or leg.vehicleid) for leg in body.legs):
        raise HTTPException(400, "A will-call gets its driver once the passenger calls and it has a pickup time.")
    for n, leg in enumerate(body.legs, start=1):
        # Placed once, here, so the dispatch screen can sort by distance later without
        # geocoding the same address on every page load.
        here = wheremap.place(leg.pickupplace)
        there = wheremap.place(leg.dropoffplace)
        legrec = newid()
        run(conn, """
            INSERT INTO triplegs (recordid, accountid, tripid, legnumber, driverid, vehicleid,
                                  vehicleexternal, pickupat, dropoffat, appointmentat, readyabout, returnplan,
                                  responsibility, responsibilitynote, pickupplace, pickuplat,
                                  pickuplng, dropoffplace, dropofflat, dropofflng,
                                  servicelevel, loaded, signature, gps, added)
            VALUES (:id, :a, :t, :n, :d, :v, :vx, :pa, :da, :appt, :ready, :rp, :resp, :respnote, :pp, :plat, :plng, :dp, :dlat,
                    :dlng, :svc, :loaded, 0, 0, :now)
        """, id=legrec, a=acct, t=tripid, n=n, d=leg.driverid, v=leg.vehicleid, appt=leg.appointmentat,
            ready=leg.readyabout if leg.pickupat is None else None,
            rp=leg.returnplan if leg.pickupat is None and leg.returnplan != "broker" else None,
            # A return is ours until somebody else has confirmed it: asking the broker is a hand-back.
            resp=None if n == 1 else ("provider" if leg.responsibility in (None, "broker") else leg.responsibility),
            respnote=(leg.responsibilitynote or "").strip().upper()[:255] or None if leg.responsibility == "other" else None,
            vx=(row(conn, "SELECT externalid FROM vehicles WHERE recordid = :v", v=leg.vehicleid)
                or {}).get("externalid") if leg.vehicleid else None,
            pa=leg.pickupat, da=leg.dropoffat,
            pp=leg.pickupplace.strip()[:255], plat=here[0] if here else None,
            plng=here[1] if here else None,
            dp=leg.dropoffplace.strip()[:255], dlat=there[0] if there else None,
            dlng=there[1] if there else None, svc=body.servicelevel,
            # The passenger is aboard on every leg a booking creates: the office books the
            # journey they are paying for. The empty run out to collect somebody is a
            # separate leg the driver's own record makes, not one typed in here.
            loaded=1, now=utcnow())

        # The history behind the columns, written by the endpoint that sets them. Booking a trip
        # straight onto a driver is an assignment like any other - it was just the first one - and
        # without this row the trip has no record of who was put on it or when. "Someone Is Out"
        # then has nothing to end, and the leg's own timeline opens with the driver already there
        # as though nobody ever decided it.
        # Booked straight onto a driver: the same hard blocks an assignment answers to, which
        # nobody can override. Booking is not a way round Assign.
        if leg.driverid:
            said = dispatch.for_leg(conn, acct, legrec, only={leg.driverid},
                                    vehicle_of={leg.driverid: leg.vehicleid} if leg.vehicleid else None)
            who = next((d for d in (said or {}).get("drivers", []) if d["driverid"] == leg.driverid), None)
            unit = next((v for v in (said or {}).get("vehicles", []) if v["vehicleid"] == leg.vehicleid), None)
            if not who:
                raise HTTPException(404, "No such driver on this account")
            for x, name in ((who, (who.get("name") or "").title()), (unit, (unit or {}).get("externalid") or "")):
                if x and x["blocked"]:
                    raise HTTPException(409, f"Not booked. {name} cannot take this trip: {x['blocked'][0]}")
        if leg.driverid or leg.vehicleid:
            run(conn, """
                INSERT INTO tripassignments (recordid, accountid, legid, driverid, vehicleid,
                                             assignedon, assignedby)
                VALUES (:id, :a, :l, :d, :v, :now, :by)
            """, id=newid(), a=acct, l=legrec, d=leg.driverid, v=leg.vehicleid,
                now=utcnow(), by=user["recordid"])
            _shadow_check(conn, acct, leg.driverid, leg.vehicleid, legrec, user["recordid"])
        # Somebody has to be able to take it, or it is not booked. Asked of the leg as written, so
        # the answer is the one an assignment would get.
        if leg.pickupat is not None and not leg.driverid:
            why = dayplan.availability(conn, acct, legrec)
            if why:
                raise HTTPException(409, "Not booked. " + _doubt(conn, acct, legrec) + " ".join(why[:1]) +
                                    (" " + "; ".join(why[1:]) + "." if why[1:] else ""))
        # The ride home is the broker's to arrange: handed back now, ours until they confirm it.
        if n > 1 and leg.responsibility == "broker":
            _hand_back_leg(conn, acct, user, {"recordid": tripid, "externalid": external},
                           {"recordid": legrec, "driverid": None, "pickupat": None}, "outsidehours",
                           "RETURN ARRANGED WITH THE BROKER WHEN BOOKED: IT COULD RUN PAST CLOSING")

    return {"recordid": tripid, "externalid": external}


@router.post("/trips/{tripid}/measure")
def measure_the_trip(tripid: str, request: Request, user: dict = Depends(editor),
                     conn: Connection = Depends(get_conn)):
    """Work out how far each leg actually ran, and write it down.

    From the vehicle's own fixes. Written once, when the leg has closed - a trip billed in
    March must not become a different number in June because a road moved or a fix was
    withdrawn, so this records the figure, where it came from, and how many fixes it rests
    on. Re-running it overwrites, which is deliberate: it is how a correction is made, and
    the activity log says it happened."""
    acct = user["accountid"]
    trip = row(conn, "SELECT recordid FROM trips WHERE recordid = :i AND accountid = :a "
                     "AND deleted IS NULL", i=tripid, a=acct)
    if not trip:
        raise HTTPException(404, "No such trip")
    done = []
    for leg in rows(conn, """
        SELECT recordid, legnumber, driverid, pickupat, dropoffat, pickuplat, pickuplng,
               dropofflat, dropofflng
        FROM triplegs WHERE tripid = :t AND accountid = :a ORDER BY legnumber
    """, t=tripid, a=acct):
        if not leg["dropoffat"]:
            done.append({"legnumber": leg["legnumber"], "miles": None,
                         "source": None, "why": "still open"})
            continue
        got = None
        if leg["driverid"]:
            got = wheremap.trail_miles(conn, acct, leg["driverid"],
                                       leg["pickupat"], leg["dropoffat"])
        # Two fixes is a line, not a journey. Below that the trail is not evidence and the
        # leg is left unmeasured rather than carrying a number nobody should rely on.
        if got and got["fixes"] >= 3 and got["miles"] > 0:
            run(conn, """
                UPDATE triplegs SET miles = :m, milessource = 'gps', milesfixes = :n,
                                    milesonf = :now
                WHERE recordid = :i
            """, m=got["miles"], n=got["fixes"], now=utcnow(), i=leg["recordid"])
            done.append({"legnumber": leg["legnumber"], "miles": got["miles"],
                         "source": "gps", "fixes": got["fixes"], "gaps": got["gaps"]})
        else:
            done.append({"legnumber": leg["legnumber"], "miles": None, "source": None,
                         "why": "not enough fixes to measure",
                         "fixes": (got or {}).get("fixes", 0)})
    log(conn, user, "trip-measured", "trip", tripid, {"legs": len(done)},
        ip=client_ip(request))
    saved(conn)
    return {"legs": done}


@router.get("/trips/{tripid}")
def get_trip(tripid: str, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    t = row(conn, """
        SELECT t.*, b.name AS brokername FROM trips t LEFT JOIN payers b ON b.recordid = t.brokerid
        WHERE t.recordid = :id AND t.accountid = :a AND t.deleted IS NULL
    """, id=tripid, a=acct)
    if not t:
        raise HTTPException(404, "Trip not found")
    t["legs"] = rows(conn, """
        SELECT l.recordid, l.legnumber, l.pickupat, l.dropoffat, l.appointmentat, l.readyabout, l.returnplan,
               l.brokerstate, l.responsibility, l.responsibilitynote, l.activationsource, l.activatedon,
               l.brokerreadyat, l.signature, l.gps, l.driverid, l.vehicleid,
               l.driverexternal, l.vehicleexternal, CONCAT(d.firstname, ' ', d.lastname) AS drivername,
               l.executionstate, l.outcomestate, l.pickupplace, l.dropoffplace, l.miles,
               v.externalid AS unit, v.modelyear
        FROM triplegs l LEFT JOIN drivers d ON d.recordid = l.driverid LEFT JOIN vehicles v ON v.recordid = l.vehicleid
        WHERE l.tripid = :id ORDER BY l.legnumber
    """, id=tripid)
    # What judged each leg, as it stood when it did: the rule's code, name and version, and whether
    # a reviewer had approved it.
    t["checks"] = rows(conn, """
        SELECT c.legid, c.subject, c.outcome, c.reasoncode, c.reason, c.credentialid, c.windowstart,
               c.windowend, c.rulecode AS code, c.rulename AS description, c.ruleversion AS version,
               COALESCE(c.approved, 1) AS verified, cr.number, cr.issuedon, cr.expireson,
               cr.documentid
        FROM legchecks c
        LEFT JOIN credentials cr ON cr.recordid = c.credentialid
        WHERE c.tripid = :id AND c.runid = :run
        ORDER BY c.outcome = 'pass', c.rulecode
    """, id=tripid, run=t["lastrunid"])
    t["run"] = row(conn, "SELECT recordid, reason, engineversion, finished FROM evaluationruns WHERE recordid = :r",
                   r=t["lastrunid"]) if t["lastrunid"] else None
    for leg in t["legs"]:
        leg["waits"] = rows(conn, """
            SELECT w.recordid, w.startedon, w.endedon, w.reason, w.note, w.latitude, w.longitude,
                   TIMESTAMPDIFF(MINUTE, w.startedon, COALESCE(w.endedon, UTC_TIMESTAMP())) AS minutes,
                   TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername
            FROM tripwaits w LEFT JOIN drivers d ON d.recordid = w.driverid
            WHERE w.legid = :l ORDER BY w.startedon
        """, l=leg["recordid"])
        leg["events"] = rows(conn, """
            SELECT e.state, e.happenedon, e.recordedon, e.latitude, e.longitude,
                   TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername,
                   u.name AS byname
            FROM tripevents e
            LEFT JOIN drivers d ON d.recordid = e.driverid
            LEFT JOIN users u ON u.recordid = e.byuserid
            WHERE e.legid = :l ORDER BY e.happenedon
        """, l=leg["recordid"])
        leg["assignments"] = rows(conn, """
            SELECT a.assignedon, a.endedon, a.endreason, a.override, a.overridereason,
                   a.acknowledgedon, a.declinedon,
                   TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername,
                   v.externalid AS unit, u.name AS byname
            FROM tripassignments a
            LEFT JOIN drivers d ON d.recordid = a.driverid
            LEFT JOIN vehicles v ON v.recordid = a.vehicleid
            LEFT JOIN users u ON u.recordid = a.assignedby
            WHERE a.legid = :l ORDER BY a.assignedon
        """, l=leg["recordid"])
    t["issues"] = rows(conn, """
        SELECT i.recordid, i.legid, i.kind, i.note, i.raisedon, i.latitude, i.longitude,
               i.acknowledgedon, i.resolvedon, i.resolution, i.resolutionkind,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername,
               u.name AS byname,
               -- Which unit was on the leg, so the screen showing the problem can also be the
               -- screen that takes the van off the road.
               l.vehicleid, v.externalid AS vehiclename
        FROM tripissues i
        LEFT JOIN triplegs l ON l.recordid = i.legid
        LEFT JOIN vehicles v ON v.recordid = l.vehicleid
        LEFT JOIN drivers d ON d.recordid = i.driverid
        LEFT JOIN users u ON u.recordid = i.acknowledgedby
        WHERE i.tripid = :id ORDER BY i.raisedon
    """, id=tripid)
    t["rejections"] = rows(conn, """
        SELECT r.reason, r.note, r.requestedon, r.senton, r.sentby, r.acknowledgedon,
               r.acknowledgedref, u.name AS byname
        FROM triprejections r LEFT JOIN users u ON u.recordid = r.requestedby
        WHERE r.tripid = :id ORDER BY r.requestedon
    """, id=tripid)
    # What the office did to this trip, in its own words. The log is append-only, so this is the
    # part of the record nobody can quietly correct afterwards.
    t["activity"] = rows(conn, """
        SELECT a.action, a.added, a.detail, u.name AS byname
        FROM activitylog a LEFT JOIN users u ON u.recordid = a.userid
        WHERE a.accountid = :a AND a.entitytype = 'trip' AND a.entityid = :id
        ORDER BY a.added
    """, a=acct, id=tripid)
    t["edit"] = _edit_rules(t, t["legs"])
    # Every edit, with who made it, why, and when the driver on the leg read it.
    t["changes"] = rows(conn, """
        SELECT c.legid, c.changedon, c.reason, c.changes, c.legstate, c.seenon, c.driverid,
               u.name AS byname,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername
        FROM tripchanges c LEFT JOIN users u ON u.recordid = c.changedby
        LEFT JOIN drivers d ON d.recordid = c.driverid
        WHERE c.accountid = :a AND c.tripid = :t ORDER BY c.changedon
    """, a=acct, t=tripid)
    for c in t["changes"]:
        c["changes"] = json.loads(c["changes"] or "[]")
    t["issuekinds"] = driverapp.ISSUES
    t["whatwasdone"] = {**WAS_ACTUALLY_DONE, **WHAT_WAS_DONE}
    t["waitreasons"] = driverapp.WAIT_REASONS
    t["endreasons"] = END_REASONS
    # Every text sent to a driver about this trip, and whether it went.
    t["texts"] = rows(conn, """
        SELECT x.recordid, x.kind, x.channel, x.body, x.status, x.error, x.added, x.tonumber,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername
        FROM drivertexts x LEFT JOIN drivers d ON d.recordid = x.driverid
        WHERE x.accountid = :a AND x.tripid = :t ORDER BY x.added DESC
    """, a=acct, t=tripid)
    t["returnreasons"] = RETURN_REASONS
    return t


@router.get("/trips/{tripid}/routes")
def trip_routes(tripid: str, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Each leg as it was driven: the driver's reported positions from setting off until the trip
    was over, and where it was to start and finish. A leg not driven yet has no positions - only
    its two ends."""
    acct = user["accountid"]
    if not row(conn, "SELECT 1 AS x FROM trips WHERE recordid = :t AND accountid = :a AND deleted IS NULL",
               t=tripid, a=acct):
        raise HTTPException(404, "No such trip")
    out = {}
    for leg in rows(conn, """
        SELECT recordid, driverid, pickuplat, pickuplng, dropofflat, dropofflng
        FROM triplegs WHERE tripid = :t AND accountid = :a ORDER BY legnumber
    """, t=tripid, a=acct):
        ends = row(conn, """
            SELECT MIN(happenedon) AS began, MAX(CASE WHEN state = 'completed' THEN happenedon END) AS done,
                   MAX(happenedon) AS last
            FROM tripevents WHERE legid = :l AND state IN ('enroute', 'arrived', 'onboard', 'completed')
        """, l=leg["recordid"]) or {}
        points = []
        if leg["driverid"] and ends.get("began"):
            points = [[float(p["longitude"]), float(p["latitude"])] for p in rows(conn, """
                SELECT latitude, longitude FROM driverlocations
                WHERE accountid = :a AND driverid = :d AND recordedon BETWEEN :f AND :u
                ORDER BY recordedon
            """, a=acct, d=leg["driverid"], f=ends["began"], u=ends.get("done") or utcnow())]
        def at(lat, lng):
            return [float(lng), float(lat)] if lat is not None and lng is not None else None
        out[leg["recordid"]] = {"points": points, "pickup": at(leg["pickuplat"], leg["pickuplng"]),
                                "dropoff": at(leg["dropofflat"], leg["dropofflng"]),
                                "driven": bool(ends.get("done"))}
    return {"style": wheremap.style_url(), "legs": out}


@router.get("/trips/{tripid}/phi")
def get_trip_phi(tripid: str, request: Request, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    if not row(conn, "SELECT 1 AS x FROM trips WHERE recordid = :id AND accountid = :a", id=tripid, a=acct):
        raise HTTPException(404, "Trip not found")
    legs = [l["recordid"] for l in rows(conn, "SELECT recordid FROM triplegs WHERE tripid = :id", id=tripid)]
    legphi = phi.get_many(conn, acct, "leg", legs)
    log(conn, user, "view", "trip", tripid, {"fields": "member,addresses"}, phi=True, ip=client_ip(request))
    return {"member": phi.get(conn, acct, "trip", tripid) or {},
            "legs": {lid: {k: v for k, v in p.items() if k != "raw"} for lid, p in legphi.items()}}


class TripPatch(BaseModel):
    billingstatus: str


@router.patch("/trips/{tripid}")
def patch_trip(tripid: str, body: TripPatch, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    if body.billingstatus not in ("unbilled", "billed", "paid", "held"):
        raise HTTPException(400, "Unknown billing status")
    # Taken by the on-call driver after closing: billed only once the office has looked at it.
    if body.billingstatus in ("billed", "paid") and row(conn, """
            SELECT 1 AS x FROM triplegs WHERE tripid = :t AND accountid = :a
               AND selfassignedon IS NOT NULL AND afterhoursreviewedon IS NULL""", t=tripid, a=user["accountid"]):
        raise HTTPException(409, "An on-call driver took part of this trip after closing. Review it "
                                 "(Dispatch, Needs Attention) before it is billed.")
    # Nothing is billed from a record nobody has read.
    if body.billingstatus in ("billed", "paid") and not row(conn, """
            SELECT 1 AS x FROM trips WHERE recordid = :t AND accountid = :a AND verifystate = 'verified'""",
                                                            t=tripid, a=user["accountid"]):
        raise HTTPException(409, "Bill this trip from the Billing page.")
    r = run(conn, "UPDATE trips SET billingstatus = :s, updated = :now WHERE recordid = :id AND accountid = :a",
            s=body.billingstatus, now=utcnow(), id=tripid, a=user["accountid"])
    if not r.rowcount:
        raise HTTPException(404, "Trip not found")
    log(conn, user, "update", "trip", tripid, {"billingstatus": body.billingstatus})
    return {"ok": True}


# ------------------------------------------------------------------------------------------------
# Editing a booked trip
# ------------------------------------------------------------------------------------------------
# A mistake in a booking has to be put right, and how much may be changed depends on how far the
# trip has got. Before anybody has set off, everything. On the road, only where the passenger is
# going - the pickup, the day, the service and the payer have already happened. A finished leg,
# nothing: what happened is what was recorded. Billed, cancelled or handed back to the broker,
# nothing either - a correction then is the payer's.
#
# Every edit is written down field by field, and a driver already on a leg has to say they have
# read it before the leg moves on. A broker's trip needs a reason for every change, because the
# broker's manifest is what they will pay against and the trip has to say why it differs.

MOVING = ("enroute", "arrived", "onboard")
STAGE_SAID = {"moving": "the trip has started", "done": "the leg is finished",
              "closed": "the leg is closed"}


def _stage(leg: dict) -> str:
    if leg["outcomestate"]:
        return "closed"
    if leg["executionstate"] == "completed":
        return "done"
    return "moving" if leg["executionstate"] in MOVING else "open"


def _edit_rules(trip: dict, legs: list[dict]) -> dict:
    """What may be changed on this trip now, said the same way to the screen that offers the edit
    and to the endpoint that takes it."""
    locked = None
    if trip["cancelledon"]:
        locked = "This trip is canceled. Nothing on it can be changed."
    elif trip["brokerstate"] in ("returnpending", "returned"):
        locked = "This trip has been returned to the broker. Nothing on it can be changed."
    elif trip["billingstatus"] in ("billed", "paid"):
        locked = ("This trip has been billed. A correction now is an adjustment with the payer, "
                  "not an edit.")
    stages = {l["recordid"]: _stage(l) for l in legs}
    if not locked and stages and all(s in ("done", "closed") for s in stages.values()):
        locked = "This trip is finished. A completed trip cannot be changed."
    return {"locked": locked, "legs": stages,
            # The passenger, the payer and the service are the trip's own facts: once any leg is
            # under way they have happened.
            "tripfields": all(s == "open" for s in stages.values()),
            "reasonrequired": bool(trip["brokerid"]) or any(s != "open" for s in stages.values())}


class LegEdit(BaseModel):
    legid: str
    pickupat: datetime | None = None
    dropoffat: datetime | None = None
    appointmentat: datetime | None = None
    pickupplace: str | None = None
    dropoffplace: str | None = None
    miles: float | None = None
    readyabout: datetime | None = None    # a will-call return only
    returnplan: str | None = None         # a will-call return only: RETURN_PLANS, or "" for none
    responsibility: str | None = None     # a return: RESPONSIBILITY
    responsibilitynote: str | None = None


class TripEdit(BaseModel):
    """The trip as it should now read - every field, not only the changed ones. What differs from
    what is on file is the edit."""
    passenger: str
    passengerphone: str | None = None
    servicelevel: str
    payer: str = "private"
    brokerid: str | None = None
    brokertripno: str | None = None
    note: str | None = None
    reason: str | None = None
    critical: bool | None = None          # the office's own flag: no driver is told, no reason asked
    legs: list[LegEdit] = []


def _said(v) -> str:
    """A value as the record keeps it: as a person reads it, not as the database holds it."""
    if v is None or v == "":
        return "-"
    if isinstance(v, datetime):
        return v.strftime("%m/%d/%Y %-I:%M %p")
    return str(v)


@router.put("/trips/{tripid}")
def edit_trip(tripid: str, body: TripEdit, request: Request, user: dict = Depends(editor),
              conn: Connection = Depends(get_conn)):
    """Put right a booked trip, within what its stage allows.

    The assigned driver and vehicle are put to the same check an assignment goes through, with the
    trip as it will now read: an edit that leaves somebody on a leg they can no longer lawfully
    take - ambulatory made wheelchair, in a van with no lift - is refused, not saved and warned
    about afterwards."""
    acct = user["accountid"]
    trip = row(conn, """
        SELECT t.*, b.name AS brokername FROM trips t LEFT JOIN payers b ON b.recordid = t.brokerid
        WHERE t.recordid = :t AND t.accountid = :a AND t.deleted IS NULL
    """, t=tripid, a=acct)
    if not trip:
        raise HTTPException(404, "No such trip")
    legs = rows(conn, """
        SELECT recordid, legnumber, pickupat, dropoffat, appointmentat, readyabout, returnplan, brokerstate,
               responsibility, responsibilitynote,
               pickupplace, dropoffplace, miles, driverid, vehicleid, executionstate, outcomestate
        FROM triplegs WHERE tripid = :t AND accountid = :a ORDER BY legnumber
    """, t=tripid, a=acct)
    rules = _edit_rules(trip, legs)
    if rules["locked"]:
        raise HTTPException(409, rules["locked"])
    if body.servicelevel not in dispatch.SERVICE:
        raise HTTPException(400, f"Unknown service level {body.servicelevel}")
    if not body.passenger.strip():
        raise HTTPException(400, "Give the passenger's name")

    def payername(pid):
        if not pid:
            return "Private pay"
        return (row(conn, "SELECT name FROM payers WHERE recordid = :p", p=pid) or {}).get("name") or pid

    # The trip's own fields.
    tripchanges = []
    def compare(label, old, new, *, needsopen=True, shown=None):
        if (old or None) == (new or None):
            return False
        if needsopen and not rules["tripfields"]:
            raise HTTPException(409, f"{label} cannot be changed once the trip has started.")
        tripchanges.append({"field": label, "old": shown(old) if shown else _said(old),
                            "new": shown(new) if shown else _said(new)})
        return True
    passenger = " ".join(body.passenger.split()).upper()[:160]
    compare("Passenger", trip["passenger"], passenger)
    phone = (body.passengerphone or "").strip()[:32] or None
    compare("Telephone", trip["passengerphone"], phone, needsopen=False)
    servicechanged = compare("Service", trip["servicelevel"], body.servicelevel,
                             shown=lambda v: dispatch.SERVICE.get(v, {}).get("label", v) if v else "-")
    payerchanged = compare("Payer", trip["brokerid"], body.brokerid or None, shown=payername)
    note = (body.note or "").strip()[:512] or None
    compare("Note", trip["note"], note, needsopen=False)

    # Each leg's, within its own stage.
    given = {l.legid: l for l in body.legs}
    unknown = set(given) - {l["recordid"] for l in legs}
    if unknown:
        raise HTTPException(400, "That leg is not on this trip")
    legchanges: dict[str, list] = {}
    updates: dict[str, dict] = {}
    for leg in legs:
        want = given.get(leg["recordid"])
        if not want:
            continue
        stage = rules["legs"][leg["recordid"]]
        mine, upd = [], {}
        allowed = {"open": ("pickupat", "appointmentat", "pickupplace", "dropoffplace", "readyabout", "returnplan",
                            "responsibility", "responsibilitynote"),
                   "moving": ("dropoffplace",),
                   "done": (),
                   "closed": ()}[stage]
        for field, label in (("pickupat", "Pickup time"), ("appointmentat", "Appointment time"),
                             ("dropoffat", "Drop-off time"),
                             ("pickupplace", "Pickup address"), ("dropoffplace", "Drop-off address"),
                             ("miles", "Miles"), ("readyabout", "Ready about"), ("returnplan", "Return plan"),
                             ("responsibility", "Who brings them home"), ("responsibilitynote", "Other provider")):
            new = getattr(want, field)
            # Who brings them home belongs to a return leg. Asking the broker is a hand-back, made
            # below; the return stays ours until they confirm.
            if field in ("responsibility", "responsibilitynote"):
                if leg["legnumber"] == 1 or new is None:
                    continue
                if field == "responsibility":
                    if new not in RESPONSIBILITY:
                        raise HTTPException(400, "Unknown answer to who brings them home")
                    if new == "broker":
                        if not (body.brokerid or trip["brokerid"]):
                            raise HTTPException(400, "Only a broker's trip can have the broker arrange the return.")
                        if not leg["brokerstate"]:
                            upd["handback"] = True
                            mine.append({"field": "Who brings them home" if len(legs) == 1 else
                                         f"Leg {leg['legnumber']} who brings them home",
                                         "old": RESPONSIBILITY.get(leg["responsibility"] or "provider"),
                                         "new": "Asked the broker to take it"})
                        continue
                    if new == "other" and not ((want.responsibilitynote or "").strip() or leg["responsibilitynote"]):
                        raise HTTPException(400, "Say which provider is bringing them home, and their confirmation.")
                else:
                    new = new.strip().upper()[:255] or None
            # Ready About and the return plan belong to a will-call still waiting for its call.
            if field in ("readyabout", "returnplan") and (leg["pickupat"] is not None or new is None):
                continue
            if field == "returnplan":
                if new and new not in RETURN_PLANS:
                    raise HTTPException(400, "Unknown return plan")
                if leg["brokerstate"] and new != leg["returnplan"]:
                    raise HTTPException(409, "This ride home is with the broker already; its plan cannot change.")
                if new == "broker" and not (body.brokerid or trip["brokerid"]):
                    raise HTTPException(400, "Only a broker's trip can have the broker arrange the return.")
                new = new or None
            if field in ("pickupplace", "dropoffplace"):
                new = " ".join((new or "").split()).upper()[:255] or None
                if new is None:
                    continue                     # an address is never blanked by an edit
            if field == "miles" and new is not None:
                new = round(float(new), 1)
                dispatch.plausible_miles(new)
            old = leg[field]
            if field == "miles" and old is not None:
                old = round(float(old), 1)
            if new is None and field in ("pickupat", "appointmentat", "dropoffat", "miles"):
                continue
            if old == new:
                continue
            if field not in allowed:
                raise HTTPException(409, f"Leg {leg['legnumber']}: {label.lower()} cannot be changed "
                                         f"once {STAGE_SAID.get(stage, 'it has started')}.")
            mine.append({"field": f"{label}" if len(legs) == 1 else f"Leg {leg['legnumber']} {label.lower()}",
                         "old": _said(old), "new": _said(new)})
            upd[field] = new
        if stage == "done" and upd.get("pickupat") and (upd.get("dropoffat") or leg["dropoffat"]) \
                and (upd.get("dropoffat") or leg["dropoffat"]) < upd["pickupat"]:
            raise HTTPException(400, f"Leg {leg['legnumber']}: the drop-off cannot be before the pickup.")
        if mine:
            legchanges[leg["recordid"]] = mine
            updates[leg["recordid"]] = upd

    # Critical or not is the office's ordering of its own work: nothing the driver runs, nothing a
    # broker pays against. Changed on its own it is kept and logged, and nobody is asked why.
    critical = trip["critical"] if body.critical is None else int(body.critical)
    criticalchanged = critical != trip["critical"]
    # A will-call that could now run past closing needs its plan, as when it was booked.
    for leg in legs:
        if leg["pickupat"] is not None or leg["outcomestate"]:
            continue
        upd = updates.get(leg["recordid"], {})
        ready = upd.get("readyabout") or leg["readyabout"]
        if not ready:
            continue
        got = after_hours(conn, acct, ready.date(), ready, upd.get("pickupplace") or leg["pickupplace"],
                          upd.get("dropoffplace") or leg["dropoffplace"])
        resp = upd.get("responsibility", leg["responsibility"])
        decided = (upd.get("returnplan", leg["returnplan"]) or upd.get("handback") or leg["brokerstate"]
                   or resp in ("other", "unconfirmed"))
        if got["needsplan"] and not decided:
            # We bring them home, past closing: that is the on-call driver.
            if resp == "provider":
                upd["returnplan"] = "oncall"
                updates[leg["recordid"]] = upd
                legchanges.setdefault(leg["recordid"], [])
            else:
                raise HTTPException(409, _plan_said(ready.date(), got))
    if not tripchanges and not legchanges:
        if not criticalchanged:
            raise HTTPException(400, "Nothing was changed.")
        run(conn, "UPDATE trips SET critical = :c, updated = :now WHERE recordid = :t AND accountid = :a",
            c=critical, now=utcnow(), t=tripid, a=acct)
        log(conn, user, "trip-edited", "trip", tripid, {"critical": bool(critical)}, ip=client_ip(request))
        saved(conn)
        return {"ok": True}
    reason = (body.reason or "").strip()
    touched_started = any(rules["legs"][lid] != "open" for lid in legchanges) or (
        tripchanges and not rules["tripfields"])
    if (trip["brokerid"] or touched_started) and not reason:
        raise HTTPException(400, "Say why it is being changed." if not trip["brokerid"] else
                            "This is a broker's trip. Say why it is being changed - the broker's "
                            "manifest is what they will pay against.")

    # Who is on each leg still to run, and what - if anything - already stands against them. An
    # edit is refused only for what IT puts in the way: a driver blocked before the edit for some
    # other reason is the dispatcher's to deal with, and must not stop a telephone number being
    # corrected.
    def standing(leg):
        said = dispatch.for_leg(conn, acct, leg["recordid"])
        out = {}
        for kind, rid in (("driver", leg["driverid"]), ("vehicle", leg["vehicleid"])):
            who = next((c for c in said[f"{kind}s"] if rid and c[f"{kind}id"] == rid), None)
            if who:
                out[kind] = (who["name"], set(who["blocked"]))
        return out
    onlegs = [l for l in legs if l["driverid"] and rules["legs"][l["recordid"]] in ("open", "moving")]
    before = {l["recordid"]: standing(l) for l in onlegs}

    now = utcnow()
    # The trip's fields.
    first = updates.get(legs[0]["recordid"], {}) if legs else {}
    tripdate = first["pickupat"].date() if first.get("pickupat") and \
        rules["legs"][legs[0]["recordid"]] == "open" else trip["tripdate"]
    origin = tripcheck.pickup_state(first.get("pickupplace") or legs[0]["pickupplace"]) if legs else None
    if (body.brokerid or None) and (payerchanged or tripdate != trip["tripdate"] or first.get("pickupplace")):
        if not tripcheck.contract_for(conn, acct, body.brokerid, tripdate, origin):
            raise HTTPException(400, tripcheck.no_line(conn, acct, body.brokerid, origin))
    run(conn, """
        UPDATE trips SET passenger = :p, passengerphone = :ph, servicelevel = :svc, brokerid = :b, brokertripno = :btn,
                         payer = :pay, note = :n, tripdate = :on, critical = :crit, updated = :now
        WHERE recordid = :t AND accountid = :a
    """, p=passenger, ph=phone, svc=body.servicelevel, b=body.brokerid or None, crit=critical,
        btn=((body.brokertripno or "").strip().upper()[:40] or None) if body.brokerid else None,
        pay=(body.payer or "private")[:16], n=note, on=tripdate, now=now, t=tripid, a=acct)
    # A trip booked here was priced here; if what it is priced on has changed, it is priced again.
    # One that came from a broker arrived with the broker's figure and keeps it.
    if trip["bookedby"] and (servicechanged or payerchanged or tripdate != trip["tripdate"]):
        priced = rateset.quote(conn, acct, payerid=body.brokerid or None,
                               servicelevel=body.servicelevel, on=tripdate, legs=len(legs),
                               state=origin)
        run(conn, "UPDATE trips SET billedamount = :amt, scheduleid = :s WHERE recordid = :t",
            amt=priced["amount"] or 0, s=priced["scheduleid"], t=tripid)
    if servicechanged:
        run(conn, "UPDATE triplegs SET servicelevel = :svc WHERE tripid = :t AND accountid = :a",
            svc=body.servicelevel, t=tripid, a=acct)
    # The legs'.
    for lid, upd in updates.items():
        sets, params = [], {"l": lid, "a": acct}
        for field, value in upd.items():
            if field == "handback":
                continue
            sets.append(f"{field} = :{field}")
            params[field] = value
            if field in ("pickupplace", "dropoffplace"):
                spot = wheremap.place(value)
                pre = "pickup" if field == "pickupplace" else "dropoff"
                sets += [f"{pre}lat = :{pre}lat", f"{pre}lng = :{pre}lng"]
                params[f"{pre}lat"], params[f"{pre}lng"] = (spot or (None, None))
            if field == "miles":
                sets.append("milessource = 'office'")
        if sets:
            run(conn, f"UPDATE triplegs SET {', '.join(sets)} WHERE recordid = :l AND accountid = :a", **params)

    # A ride home the broker is now to arrange is handed back to them, as at booking.
    for lid, upd in updates.items():
        if upd.get("returnplan") == "broker" or upd.get("handback"):
            _hand_back_leg(conn, acct, user, trip, next(l for l in legs if l["recordid"] == lid),
                           "outsidehours", "RETURN ARRANGED WITH THE BROKER: IT COULD RUN PAST CLOSING")

    # A leg nobody is on yet, changed in a way that changes who could take it, is asked again: if
    # nobody could now, the change is not made.
    for leg in legs:
        moved = leg["recordid"] in updates or servicechanged or payerchanged
        if moved and not leg["driverid"] and rules["legs"][leg["recordid"]] == "open" and not leg["outcomestate"]:
            why = dayplan.availability(conn, acct, leg["recordid"])
            if why:
                raise HTTPException(409, "Not changed. " + _doubt(conn, acct, leg["recordid"]) + " ".join(why[:1]) +
                                    (" " + "; ".join(why[1:]) + "." if why[1:] else ""))

    # Whoever is on a leg still to run is checked against the trip as it now reads.
    for leg in onlegs:
        for kind, (name, blocks) in standing(leg).items():
            new = sorted(blocks - before[leg["recordid"]].get(kind, (name, set()))[1])
            if new:
                raise HTTPException(409, f"Not changed: {name} could no longer take leg "
                                         f"{leg['legnumber']} - {new[0]}. Change the {kind} "
                                         f"first, or leave the trip as it was.")

    # The record of it: one row per leg it touched, and the driver on that leg has to read it.
    written = 0
    for leg in legs:
        stage = rules["legs"][leg["recordid"]]
        mine = legchanges.get(leg["recordid"], [])
        if not mine and not (tripchanges and stage in ("open", "moving")):
            continue
        tell = leg["driverid"] if stage in ("open", "moving") else None
        run(conn, """
            INSERT INTO tripchanges (recordid, accountid, tripid, legid, changedon, changedby, reason,
                                     changes, driverid, legstate)
            VALUES (:id, :a, :t, :l, :now, :by, :r, :c, :d, :st)
        """, id=newid(), a=acct, t=tripid, l=leg["recordid"], now=now, by=user["recordid"],
            r=reason[:2000] or None, c=json.dumps(tripchanges + mine), d=tell,
            st=leg["outcomestate"] or leg["executionstate"])
        written += 1
        if tell:
            what = ", ".join(dict.fromkeys(c["field"].lower() for c in tripchanges + mine))
            sms.tell(conn, acct, tell, "changed",
                     f"Trip {trip['externalid']} changed: {what}. Open the app and tap I Have Seen This.",
                     tripid, leg["recordid"])
    if not written:
        run(conn, """
            INSERT INTO tripchanges (recordid, accountid, tripid, legid, changedon, changedby, reason, changes)
            VALUES (:id, :a, :t, NULL, :now, :by, :r, :c)
        """, id=newid(), a=acct, t=tripid, now=now, by=user["recordid"], r=reason[:2000] or None,
            c=json.dumps(tripchanges))
    if any(l["driverid"] for l in legs):
        evaluate(conn, acct, tripids=[tripid], userid=user["recordid"], reason="edit")
    log(conn, user, "trip-edited", "trip", tripid,
        {"changes": tripchanges + [c for v in legchanges.values() for c in v], "reason": reason or None,
         **({"critical": bool(critical)} if criticalchanged else {})},
        ip=client_ip(request))
    # Verified as it read then: changed, it is read again.
    run(conn, "UPDATE trips SET verifystate = 'awaitingreview', reviewedon = NULL, reviewedby = NULL "
              "WHERE recordid = :t AND accountid = :a AND verifystate = 'verified'", t=tripid, a=acct)
    saved(conn)
    return {"ok": True}


class ReleaseIn(BaseModel):
    pickupat: datetime
    pickupplace: str | None = None    # where they are now, when it is not where they were left
    note: str | None = None


@router.post("/legs/{legid}/release")
def passenger_called(legid: str, body: ReleaseIn, request: Request, user: dict = Depends(editor),
                     conn: Connection = Depends(get_conn)):
    """The passenger on a will-call return has rung to be collected.

    The leg gets its pickup time, and from then on it is an ordinary leg - on the board at that
    time, late and missed like any other. A driver already on it is told the same way an edit tells
    them, and has to say they have read it: "go and collect them now" is the whole message."""
    acct = user["accountid"]
    leg = row(conn, """
        SELECT l.recordid, l.tripid, l.pickupat, l.pickupplace, l.driverid, l.executionstate, l.outcomestate,
               COALESCE(l.brokerstate, t.brokerstate) AS brokerstate
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        WHERE l.recordid = :l AND l.accountid = :a
    """, l=legid, a=acct)
    if not leg:
        raise HTTPException(404, "No such leg")
    if leg["pickupat"] is not None:
        raise HTTPException(409, "This leg already has a pickup time.")
    if leg["outcomestate"] or leg["executionstate"] == "completed":
        raise HTTPException(409, "This leg is closed.")
    # The broker is bringing them home: the call is the broker's to take.
    if leg["brokerstate"] in ("returnpending", "returned"):
        raise HTTPException(409, "This ride home has been handed back to the broker.")
    now = utcnow()
    changes = [{"field": "Pickup time", "old": "Will-call", "new": _said(body.pickupat)}]
    run(conn, "UPDATE triplegs SET pickupat = :p WHERE recordid = :l AND accountid = :a",
        p=body.pickupat, l=legid, a=acct)
    # Discharged from another door, or moved to another facility: collected where they are now.
    moved = " ".join((body.pickupplace or "").split()).upper()[:255]
    if moved and moved != (leg["pickupplace"] or ""):
        spot = wheremap.place(moved) or (None, None)
        run(conn, "UPDATE triplegs SET pickupplace = :pp, pickuplat = :la, pickuplng = :lg "
                  "WHERE recordid = :l AND accountid = :a", pp=moved, la=spot[0], lg=spot[1], l=legid, a=acct)
        changes.append({"field": "Pickup address", "old": leg["pickupplace"], "new": moved})
    note = (body.note or "").strip()
    run(conn, """
        INSERT INTO tripchanges (recordid, accountid, tripid, legid, changedon, changedby, reason,
                                 changes, driverid, legstate)
        VALUES (:id, :a, :t, :l, :now, :by, :r, :c, :d, :st)
    """, id=newid(), a=acct, t=leg["tripid"], l=legid, now=now, by=user["recordid"],
        r=" - ".join(x for x in ("PASSENGER CALLED", note[:1900]) if x),
        c=json.dumps(changes), d=leg["driverid"], st=leg["executionstate"])
    log(conn, user, "trip-released", "trip", leg["tripid"],
        {"legid": legid, "pickupat": str(body.pickupat), "pickupplace": moved or None, "note": note or None},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


# Why a will-call return is not wanted after all. Chosen, so it can be counted and reported.
NOT_NEEDED = {"otherride": "The passenger has another ride", "admitted": "The passenger was admitted",
              "passenger": "The passenger canceled the return", "other": "Something else"}


class CallIn(BaseModel):
    answer: str                       # ready | notready | notneeded
    pickupat: datetime | None = None
    pickupplace: str | None = None    # ready: where they are now
    source: str | None = None         # ACTIVATION: where the word came from
    readysince: datetime | None = None  # when the broker says the passenger was ready
    readyabout: datetime | None = None  # not ready: when they now expect to be
    reason: str | None = None
    note: str | None = None


@router.post("/legs/{legid}/call")
def will_call_answered(legid: str, body: CallIn, request: Request, user: dict = Depends(editor),
                       conn: Connection = Depends(get_conn)):
    """The passenger on a will-call return has rung - which is not always to be collected.

    Ready: the leg gets its pickup time (passenger_called). Not ready yet: the call is written down
    and the leg goes on waiting. Not needed: the return is closed as canceled, with why; the trip's
    other legs are left as they are."""
    if body.answer == "ready":
        if not body.pickupat:
            raise HTTPException(400, "Say when they are to be picked up")
        if body.source and body.source not in ACTIVATION:
            raise HTTPException(400, "Say where the call came from")
        # Activated: where the word came from, when it reached us, and when the broker says the
        # passenger was ready - two times that can be far apart, and a broker's clock may run from
        # the first. Written with the pickup time, so they stand or fall together.
        run(conn, "UPDATE triplegs SET activationsource = :s, activatedon = :now, brokerreadyat = :r "
                  "WHERE recordid = :l AND accountid = :a AND pickupat IS NULL",
            s=body.source, now=utcnow(), r=body.readysince, l=legid, a=user["accountid"])
        return passenger_called(legid, ReleaseIn(pickupat=body.pickupat, pickupplace=body.pickupplace,
                                                 note=body.note), request, user, conn)
    if body.answer not in ("notready", "notneeded"):
        raise HTTPException(400, "Say what the passenger said")
    acct = user["accountid"]
    leg = row(conn, """
        SELECT l.recordid, l.tripid, l.pickupat, l.driverid, l.executionstate, l.outcomestate,
               COALESCE(l.brokerstate, t.brokerstate) AS brokerstate
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        WHERE l.recordid = :l AND l.accountid = :a
    """, l=legid, a=acct)
    if not leg:
        raise HTTPException(404, "No such leg")
    if leg["pickupat"] is not None:
        raise HTTPException(409, "This leg already has a pickup time.")
    if leg["outcomestate"] or leg["executionstate"] == "completed":
        raise HTTPException(409, "This leg is closed.")
    # The broker is bringing them home: the call is the broker's to take.
    if leg["brokerstate"] in ("returnpending", "returned"):
        raise HTTPException(409, "This ride home has been handed back to the broker.")
    note = (body.note or "").strip()
    if body.answer == "notneeded":
        if body.reason not in NOT_NEEDED:
            raise HTTPException(400, "Say why the return is not needed")
        if body.reason == "other" and not note:
            raise HTTPException(400, "Say why the return is not needed")
        run(conn, "UPDATE triplegs SET outcomestate = 'cancelled' WHERE recordid = :l AND accountid = :a",
            l=legid, a=acct)
        said = " - ".join(x for x in ("PASSENGER CALLED", "RETURN NOT NEEDED",
                                      NOT_NEEDED[body.reason].upper(), note[:1800]) if x)
        changes = [{"field": "Return", "old": "Will-call", "new": "Not needed"}]
    else:
        # Not ready: when they now expect to be, so the will-call is not overdue from the old time.
        if not body.readyabout:
            raise HTTPException(400, "Say when they expect to be ready")
        old = row(conn, "SELECT readyabout FROM triplegs WHERE recordid = :l", l=legid)["readyabout"]
        run(conn, "UPDATE triplegs SET readyabout = :r WHERE recordid = :l AND accountid = :a",
            r=body.readyabout, l=legid, a=acct)
        said = " - ".join(x for x in ("PASSENGER CALLED", "NOT READY YET", note[:1900]) if x)
        changes = [{"field": "Ready about", "old": _said(old) if old else None, "new": _said(body.readyabout)}]
    run(conn, """
        INSERT INTO tripchanges (recordid, accountid, tripid, legid, changedon, changedby, reason,
                                 changes, driverid, legstate)
        VALUES (:id, :a, :t, :l, :now, :by, :r, :c, :d, :st)
    """, id=newid(), a=acct, t=leg["tripid"], l=legid, now=utcnow(), by=user["recordid"], r=said,
        c=json.dumps(changes), d=leg["driverid"], st=leg["executionstate"])
    log(conn, user, f"willcall-{body.answer}", "trip", leg["tripid"],
        {"legid": legid, "reason": body.reason, "note": note or None}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/evaluate")
def evaluate_all(user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    result = evaluate(conn, user["accountid"], None, user["recordid"], "manual")
    log(conn, user, "evaluate", "evaluationrun", result["runid"], result)
    return result


# ------------------------------------------------------------------------------------------------
# Dispatch: putting a driver and a vehicle on a leg
# ------------------------------------------------------------------------------------------------
# Who may do this: any staff user, because assigning work is the job of whoever is at the desk.
# Who may override a warning: only somebody holding a supervisor appointment, because an override
# is a written decision that a known risk was accepted, and it is signed.

# What a dispatcher may say when taking a trip off a driver. Written down because "the dispatcher
# changed it" and "the driver refused it" are different events with different consequences, and a
# single free-text note loses the difference the moment anybody reports on it.
END_REASONS = {"reassigned": "Reassigned", "driver-declined": "The driver declined it",
               "trip-cancelled": "The trip was canceled", "corrected": "Corrected a mistake",
               "unavailable": "The driver or vehicle became unavailable",
               "returned": "The trip was returned to the broker"}

# Why somebody or something is out. Chosen, because "off" covers a driver on holiday booked three
# weeks ago and a driver who rang in at six this morning, and only one of those is a contingency.
OUT_REASONS = {"sick": "Off sick", "timeoff": "Time off", "training": "Training",
               "breakdown": "Broken down", "maintenance": "In for maintenance",
               "accident": "In an accident", "other": "Something else"}


class AssignIn(BaseModel):
    driverid: str | None = None
    vehicleid: str | None = None
    overridereason: str | None = None


class UnassignIn(BaseModel):
    endreason: str = "reassigned"


def _supervisor(conn: Connection, user: dict) -> bool:
    """Whether this user holds a supervisor appointment on this company."""
    return bool(row(conn, """
        SELECT 1 AS x FROM companyroles
        WHERE accountid = :a AND userid = :u AND role = 'supervisor'
          AND (until IS NULL OR until > CURRENT_DATE)
    """, a=user["accountid"], u=user["recordid"]))


@router.get("/dispatch/quote")
def what_it_comes_to(servicelevel: str, on: date, payerid: str | None = None, legs: int = 1,
                     state: str | None = None, user: dict = Depends(current_user),
                     conn: Connection = Depends(get_conn)):
    """What this trip will be billed at, and which schedule says so - asked before it is booked.

    Also what the payer adds to the compliance side, because picking a broker quietly changes who
    is allowed to drive and the person booking it should be told that at the time rather than
    discovering it when the assignment picker greys out half the roster."""
    acct = user["accountid"]
    priced = rateset.quote(conn, acct, payerid=payerid, servicelevel=servicelevel, on=on, legs=legs,
                           state=state)
    # What the payer's program asks of a driver on top of what every trip asks: the rules written
    # for that program that reach this company, counted once per thing they ask for.
    program = _program_of(conn, acct, payerid, on, state)
    priced["program"] = program
    priced["extrarequirements"] = _program_requirements(conn, acct, program) if program else 0
    return priced


def _program_of(conn: Connection, accountid: str, payerid: str | None, on,
                state: str | None = None) -> str | None:
    """The program a trip billed to this payer belongs to: the payer line's contract where it says,
    otherwise the payer's kind. No payer is the passenger."""
    if not payerid:
        return "privatepay"
    contract = tripcheck.contract_for(conn, accountid, payerid, on, state)
    if contract and contract.get("program"):
        return contract["program"]
    kind = (row(conn, "SELECT category FROM payers WHERE recordid = :p", p=payerid) or {}).get("category")
    return tripcheck.PAYER_PROGRAM.get(kind or "private", "privatepay")


def _program_requirements(conn: Connection, accountid: str, program: str) -> int:
    from app import facts as factset, rules as ruleset
    company = factset.assemble(conn, accountid)["facts"]
    asked = set()
    for r in rows(conn, """
        SELECT code, qualificationcode, applieswhen FROM compliancerules
        WHERE subject = 'driver' AND effectiveto IS NULL AND program = :p
          AND (accountid IS NULL OR accountid = :a)
    """, p=program, a=accountid):
        if ruleset.applies(ruleset.condition(r["applieswhen"]), company) is not False:
            asked.add(r["qualificationcode"] or r["code"])
    return len(asked)


class OutIn(BaseModel):
    kind: str                       # driver | vehicle
    recordid: str
    fromat: datetime
    untilat: datetime
    reason: str
    note: str | None = None


def _shift_rows(conn: Connection, acct: str, driverid: str, a: datetime, b: datetime) -> list[dict]:
    """This driver's vehicle assignments that touch the time from a to b, as moments."""
    out = []
    for s in rows(conn, """
        SELECT s.recordid, s.workday, s.vehicleid, s.startsat, s.endsat, s.oncall, s.source, v.externalid AS vehiclename
        FROM dayshifts s JOIN vehicles v ON v.recordid = s.vehicleid
        WHERE s.accountid = :a AND s.driverid = :d AND s.workday BETWEEN :f AND :u
    """, a=acct, d=driverid, f=a.date() - timedelta(days=1), u=b.date()):
        s["from"], s["to"] = plan.span(s["workday"], s["startsat"], s["endsat"])
        if s["from"] < b and a < s["to"]:
            out.append(s)
    return sorted(out, key=lambda s: s["from"])


def _put_shift(conn: Connection, acct: str, driverid: str, vehicleid: str, a: datetime, b: datetime,
               source: str, by: str, oncall: int = 0) -> None:
    run(conn, """
        INSERT INTO dayshifts (recordid, accountid, workday, driverid, vehicleid, startsat, endsat,
                               oncall, source, added, addedby)
        VALUES (:id, :a, :w, :d, :v, :s, :e, :oc, :src, :now, :by)
    """, id=newid(), a=acct, w=a.date(), d=driverid, v=vehicleid, s=a.time(), e=b.time(),
        oc=oncall, src=source, now=utcnow(), by=by)


def _free_vehicle(conn: Connection, acct: str, driverid: str, f: datetime, u: datetime, outid: str,
                  by: str) -> list[dict]:
    """End the driver's vehicle assignments while they are out: what came before stays, and - back
    at a time - they have the vehicle again from then. The absence keeps the vehicle and when its
    assignment would have ended, for Driver Is Back."""
    freed = []
    for s in _shift_rows(conn, acct, driverid, f, u):
        run(conn, "DELETE FROM dayshifts WHERE recordid = :r AND accountid = :a", r=s["recordid"], a=acct)
        if s["from"] < f:
            _put_shift(conn, acct, driverid, s["vehicleid"], s["from"], f, s["source"], by, s["oncall"])
        if u < s["to"]:
            _put_shift(conn, acct, driverid, s["vehicleid"], u, s["to"], s["source"], by, s["oncall"])
        freed.append({"vehicleid": s["vehicleid"], "vehiclename": s["vehiclename"],
                      "from": max(s["from"], f), "until": min(s["to"], u)})
        if len(freed) == 1:
            run(conn, "UPDATE driverunavailable SET vehicleid = :v, vehicleuntil = :t WHERE recordid = :r",
                v=s["vehicleid"], t=s["to"], r=outid)
    return freed


@router.post("/dispatch/out")
def someone_is_out(body: OutIn, request: Request, user: dict = Depends(editor),
                   conn: Connection = Depends(get_conn)):
    """A driver or a vehicle is out, and everything that follows from it, in one action.

    This is what a contingency actually is. A dispatcher told at six in the morning that a driver
    is sick does not want to find that driver's eleven trips one at a time; they want them off
    him, visible in one list, and coverable. So: the absence is recorded, every assignment inside
    the window that has not already been driven is ended, and each of those trips is marked as
    needing somebody - which puts it under Needs Attention on the board.

    What this does NOT do is reassign anything. Who takes the 10:15 instead is a judgement about
    a person's day, and a system that quietly moved eleven trips to whoever was nearest would be
    making it eleven times without being asked."""
    acct = user["accountid"]
    if body.kind not in ("driver", "vehicle"):
        raise HTTPException(400, "Say whether it is a driver or a vehicle")
    if body.reason not in OUT_REASONS:
        raise HTTPException(400, "Say why they are out")
    if body.untilat <= body.fromat:
        raise HTTPException(400, "The end has to be after the start")
    table = "drivers" if body.kind == "driver" else "vehicles"
    who = row(conn, f"SELECT recordid FROM {table} WHERE recordid = :id AND accountid = :a "
                    "AND deleted IS NULL", id=body.recordid, a=acct)
    if not who:
        raise HTTPException(404, f"No such {body.kind}")

    outid = newid()
    run(conn, f"""
        INSERT INTO {body.kind}unavailable (recordid, accountid, {body.kind}id, fromat, untilat,
                                            reason, note, added, addedby)
        VALUES (:id, :a, :who, :f, :u, :r, :n, :now, :by)
    """, id=outid, a=acct, who=body.recordid, f=body.fromat, u=body.untilat, r=body.reason,
        n=(body.note or "").strip()[:200] or None, now=utcnow(), by=user["recordid"])
    # Their vehicle is free while they are out, for whoever is called in to cover.
    freed = _free_vehicle(conn, acct, body.recordid, body.fromat, body.untilat, outid,
                          user["recordid"]) if body.kind == "driver" else []
    # Out while on call - the driver, or the vehicle they would take: off the on-call list, so
    # nobody believes a return is covered by somebody who cannot go.
    offcall = []
    for day in (body.fromat.date() - timedelta(days=1), body.fromat.date(), body.untilat.date()):
        for o in plan.on_call(conn, acct, day):
            if o[f"{'driverid' if body.kind == 'driver' else 'vehicleid'}"] != body.recordid:
                continue
            a, b = plan.span(o["workday"], o["startsat"], o["endsat"])
            if a < body.untilat and body.fromat < b and o["recordid"] not in {x["recordid"] for x in offcall}:
                run(conn, "DELETE FROM oncall WHERE recordid = :r AND accountid = :a", r=o["recordid"], a=acct)
                offcall.append({"recordid": o["recordid"], "drivername": o["drivername"],
                                "vehiclename": o["vehiclename"], "from": a})

    # Only work still to do. A trip driven this morning is not undone by its driver going home
    # sick this afternoon - but one from earlier today that never started is still to do, and
    # comes off with the rest. A passenger already aboard stays where they are: somebody has to
    # finish that trip, or go to them, and the office is told which.
    column = "driverid" if body.kind == "driver" else "vehicleid"
    held = rows(conn, f"""
        SELECT l.recordid AS legid, l.tripid, l.pickupat, l.executionstate, t.externalid, t.passenger
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        WHERE l.accountid = :a AND l.{column} = :who
          AND l.executionstate <> 'completed' AND l.outcomestate IS NULL
          AND l.pickupat IS NOT NULL AND l.pickupat >= :day AND l.pickupat < :u
          -- From when they are out; before that, only what is already overdue. A trip later this
          -- morning, while they are still working, stays theirs.
          AND (l.pickupat >= :f OR l.pickupat < :here OR l.executionstate = 'onboard')
        ORDER BY l.pickupat
    """, a=acct, who=body.recordid, u=body.untilat, f=body.fromat,
        here=localnow(dispatch.zone(conn, acct)), day=datetime.combine(body.fromat.date(), datetime.min.time()))
    legs = [l for l in held if l["executionstate"] != "onboard"]
    aboard = [l for l in held if l["executionstate"] == "onboard"]

    now = utcnow()
    for leg in legs:
        run(conn, """
            UPDATE tripassignments SET endedon = :now, endedby = :by, endreason = 'unavailable'
            WHERE accountid = :a AND legid = :l AND endedon IS NULL
        """, now=now, by=user["recordid"], a=acct, l=leg["legid"])
        # The vehicle comes off with the driver only when it is the driver who is out: a van in
        # the shop leaves its driver free to take another van.
        if body.kind == "driver":
            run(conn, "UPDATE triplegs SET driverid = NULL WHERE recordid = :l AND accountid = :a",
                l=leg["legid"], a=acct)
        else:
            run(conn, "UPDATE triplegs SET vehicleid = NULL WHERE recordid = :l AND accountid = :a",
                l=leg["legid"], a=acct)
        _settle_dispatch_state(conn, acct, leg["tripid"])
        run(conn, "UPDATE trips SET dispatchstate = 'needsreassign', updated = :now "
                  "WHERE recordid = :t AND accountid = :a", now=now, t=leg["tripid"], a=acct)

    if legs:
        evaluate(conn, acct, tripids=sorted({l["tripid"] for l in legs}),
                 userid=user["recordid"], reason="unavailable")
        # One text for the lot, not one a trip: the driver needs to know to stop, not the list.
        if body.kind == "driver":
            # Back later the same day: say until when, so they know the rest of the day is theirs.
            back = (f" until {body.untilat:%-I:%M %p}" if body.untilat.date() == body.fromat.date()
                    and body.untilat.time() < datetime.strptime("23:59", "%H:%M").time() else "")
            sms.tell(conn, acct, body.recordid, "removed",
                     f"You have been taken off {len(legs)} trip{'s' if len(legs) > 1 else ''} from "
                     f"{sms.when(body.fromat)}{back}. Call dispatch.", None, None)
    log(conn, user, "dispatch-out", body.kind, body.recordid,
        {"reason": body.reason, "from": str(body.fromat), "until": str(body.untilat),
         "lifted": len(legs)}, ip=client_ip(request))
    saved(conn)
    keep = ("legid", "tripid", "externalid", "passenger", "pickupat")
    return {"ok": True, "lifted": len(legs), "freed": freed, "offcall": offcall,
            "trips": [{k: l[k] for k in keep} for l in legs],
            "aboard": [{k: l[k] for k in keep} for l in aboard]}


@router.get("/dispatch/out")
def who_is_out(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Who and what is out, now or soon, so a dispatcher can see it and take it back."""
    acct = user["accountid"]
    return {
        "reasons": OUT_REASONS,
        "drivers": rows(conn, """
            SELECT u.recordid, u.driverid AS who, u.fromat, u.untilat, u.reason, u.note,
                   TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS name
            FROM driverunavailable u JOIN drivers d ON d.recordid = u.driverid
            WHERE u.accountid = :a AND u.untilat > UTC_TIMESTAMP()
            ORDER BY u.fromat
        """, a=acct),
        "vehicles": rows(conn, """
            SELECT u.recordid, u.vehicleid AS who, u.fromat, u.untilat, u.reason, u.note,
                   v.externalid AS name
            FROM vehicleunavailable u JOIN vehicles v ON v.recordid = u.vehicleid
            WHERE u.accountid = :a AND u.untilat > UTC_TIMESTAMP()
            ORDER BY u.fromat
        """, a=acct),
    }


@router.delete("/dispatch/out/{kind}/{recordid}")
def back_in(kind: str, recordid: str, request: Request, user: dict = Depends(editor),
            conn: Connection = Depends(get_conn)):
    """They are back. An absence already begun ends now - the record that they were out from one
    until twenty past two is kept - and one not begun yet is taken away. Nothing is reassigned to
    them automatically: the trips were covered by somebody while they were away, and taking them
    back is a decision."""
    if kind not in ("driver", "vehicle"):
        raise HTTPException(404, "No such thing")
    acct = user["accountid"]
    held = row(conn, f"SELECT * FROM {kind}unavailable WHERE recordid = :id AND accountid = :a",
               id=recordid, a=acct)
    if not held:
        raise HTTPException(404, "Not found")
    here = localnow(user.get("timezone") or _account_zone(conn, acct))
    vehicle = _vehicle_back(conn, acct, held, max(here, held["fromat"]), user["recordid"]) \
        if kind == "driver" else None
    if held["fromat"] < here:
        run(conn, f"UPDATE {kind}unavailable SET untilat = :now WHERE recordid = :id AND accountid = :a",
            now=min(here, held["untilat"]), id=recordid, a=acct)
    else:
        run(conn, f"DELETE FROM {kind}unavailable WHERE recordid = :id AND accountid = :a", id=recordid, a=acct)
    log(conn, user, "dispatch-back", kind, recordid, {"at": str(here), "vehicle": vehicle},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True, "vehicle": vehicle}


def _vehicle_back(conn: Connection, acct: str, out: dict, start: datetime, by: str) -> str | None:
    """Back early: the vehicle they had, from now until its assignment would have ended - unless
    somebody has been put in it meanwhile, which is said. The assignment already waiting for them
    after a back-at time starts now instead."""
    if not out.get("vehicleid") or not out.get("vehicleuntil") or start >= out["vehicleuntil"]:
        return None
    name = (row(conn, "SELECT externalid FROM vehicles WHERE recordid = :v", v=out["vehicleid"]) or {}).get("externalid")
    waiting = next((s for s in _shift_rows(conn, acct, out["driverid"], start, out["vehicleuntil"])
                    if s["vehicleid"] == out["vehicleid"] and s["from"] >= start), None)
    end = waiting["from"] if waiting else out["vehicleuntil"]
    if start >= end:
        return None
    taken = plan.clash(conn, acct, start.date(), out["driverid"], out["vehicleid"], start.time(),
                       (waiting["to"] if waiting else end).time(), leaving=waiting["recordid"] if waiting else None)
    if taken:
        return f"{name} was not given back: {taken}"
    if waiting:
        run(conn, "UPDATE dayshifts SET startsat = :s, updated = :now WHERE recordid = :r",
            s=start.time(), now=utcnow(), r=waiting["recordid"])
    else:
        _put_shift(conn, acct, out["driverid"], out["vehicleid"], start, out["vehicleuntil"], "manual", by)
    return f"{name} is theirs again from {start:%-I:%M %p}."


# What an office actually did about a problem. Chosen rather than typed, like a cancellation
# reason and a broker rejection: a month of free text cannot answer "how often did a van have to
# come off the road", which is the question that decides whether to keep the van.
# Things only a person knows. Nobody else was on the telephone, so nobody else can say whether
# the driver got going again or whether the passenger was rung - these are asked.
WHAT_WAS_DONE = {
    "carriedon": "The driver sorted it and carried on",
    "passengertold": "The passenger was told",
    "nothing": "Nothing needed doing",
    "other": "Something else",
}

# Things the record already knows, and must not be asked about.
#
# "Another driver took the trip" is not a description, it is a piece of work: somebody has to be
# taken off the leg and somebody else put on it. Offered in a list beside the others it lets a
# dispatcher close a problem by claiming work nobody did, and the trip then reads as covered with
# no driver against it - which is worse than the problem staying open, because an open problem is
# at least still on the board.
#
# So these are worked out from what has actually changed since the driver reported it, and offered
# only when they are true.
WAS_ACTUALLY_DONE = {
    "vehiclechanged": "Another vehicle was put on the trip",
    "driverchanged": "Another driver took the trip",
    "vehicleoff": "The vehicle was taken off the road",
    "cancelled": "The trip was canceled",
}


class ResolveIn(BaseModel):
    kind: str | None = None
    resolution: str | None = None


def _issue_in_context(conn: Connection, accountid: str, issueid: str) -> dict | None:
    """An issue, with the vehicle that was on its leg AT THE TIME it was raised.

    Not the one on the leg now: taking a vehicle off the road clears it from its legs, so reading
    the leg afterwards says there was never a vehicle and the problem loses its subject - the van
    it was about."""
    issue = row(conn, """
        SELECT i.recordid, i.tripid, i.legid, i.raisedon, i.driverid,
               COALESCE((SELECT a2.vehicleid FROM tripassignments a2
                          WHERE a2.legid = i.legid AND a2.assignedon <= i.raisedon
                            AND (a2.endedon IS NULL OR a2.endedon >= i.raisedon)
                          ORDER BY a2.assignedon DESC LIMIT 1), l.vehicleid) AS vehicleid
        FROM tripissues i
        LEFT JOIN triplegs l ON l.recordid = i.legid
        WHERE i.recordid = :i AND i.accountid = :a
    """, i=issueid, a=accountid)
    if issue:
        issue["vehiclename"] = (row(conn, "SELECT externalid FROM vehicles WHERE recordid = :v",
                                    v=issue["vehicleid"]) or {}).get("externalid") \
            if issue["vehicleid"] else None
    return issue


def _what_changed(conn: Connection, accountid: str, issue: dict) -> dict:
    """What has actually been done to this leg since the driver reported the problem.

    Read from the record rather than asked, so that closing a problem as "another driver took it"
    is possible only when another driver really did."""
    out: dict[str, str] = {}
    since, legid = issue["raisedon"], issue["legid"]
    if not legid:
        return out
    for a in rows(conn, """
        SELECT a.driverid, a.vehicleid, a.assignedon,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername,
               v.externalid AS vehiclename
        FROM tripassignments a
        LEFT JOIN drivers d ON d.recordid = a.driverid
        LEFT JOIN vehicles v ON v.recordid = a.vehicleid
        WHERE a.accountid = :a AND a.legid = :l AND a.assignedon > :since AND a.endedon IS NULL
        ORDER BY a.assignedon
    """, a=accountid, l=legid, since=since):
        if a["driverid"] and a["driverid"] != issue.get("driverid"):
            out["driverchanged"] = f"{a['drivername']} put on the trip"
        if a["vehiclename"] and a["vehiclename"] != issue.get("vehiclename"):
            out["vehiclechanged"] = f"{a['vehiclename']} put on the trip"
    if issue.get("vehicleid") and row(conn, """
        SELECT 1 AS x FROM vehicleunavailable
        WHERE accountid = :a AND vehicleid = :v AND added >= :since LIMIT 1
    """, a=accountid, v=issue["vehicleid"], since=since):
        out["vehicleoff"] = f"{issue.get('vehiclename') or 'The vehicle'} taken off the road"
    if row(conn, """
        SELECT 1 AS x FROM trips WHERE recordid = :t AND accountid = :a AND cancelledon >= :since
    """, t=issue["tripid"], a=accountid, since=since):
        out["cancelled"] = "The trip was cancelled"
    return out


@router.get("/issues/{issueid}/changed")
def what_changed(issueid: str, user: dict = Depends(current_user),
                 conn: Connection = Depends(get_conn)):
    """What has been done about this problem already, so the screen can offer those - and only
    those - as ways of closing it."""
    acct = user["accountid"]
    issue = _issue_in_context(conn, acct, issueid)
    if not issue:
        raise HTTPException(404, "No such issue")
    changed = _what_changed(conn, acct, issue)
    return {"changed": changed, "asked": WHAT_WAS_DONE,
            "offer": {**{k: WAS_ACTUALLY_DONE[k] for k in changed}, **WHAT_WAS_DONE}}


@router.get("/issues/unseen")
def unseen_problems(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Problems a driver has reported that nobody in the office has seen yet - what the alert that
    pops up on every page shows, until somebody presses Seen or Deal With It."""
    found = rows(conn, """
        SELECT i.recordid, i.kind, i.note, i.raisedon, i.legid, i.tripid, l.pickupat,
               t.externalid, t.passenger,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername
        FROM tripissues i
        JOIN trips t ON t.recordid = i.tripid AND t.deleted IS NULL
        LEFT JOIN triplegs l ON l.recordid = i.legid
        LEFT JOIN drivers d ON d.recordid = i.driverid
        WHERE i.accountid = :a AND i.resolvedon IS NULL AND i.acknowledgedon IS NULL
        ORDER BY i.raisedon
    """, a=user["accountid"])
    return {"items": found, "kinds": driverapp.ISSUES}


@router.post("/issues/{issueid}/seen")
def seen_it(issueid: str, request: Request, user: dict = Depends(editor),
            conn: Connection = Depends(get_conn)):
    """A dispatcher has read it. Not the same as the problem going away, which is why it is its
    own moment: a driver on the hard shoulder wants to know somebody picked up, and an office
    that cannot show when it did has no answer when asked afterwards."""
    acct = user["accountid"]
    if not row(conn, "SELECT recordid FROM tripissues WHERE recordid = :i AND accountid = :a",
               i=issueid, a=acct):
        raise HTTPException(404, "No such issue")
    run(conn, """
        UPDATE tripissues SET acknowledgedon = :now, acknowledgedby = :by
        WHERE recordid = :i AND accountid = :a AND acknowledgedon IS NULL
    """, now=utcnow(), by=user["recordid"], i=issueid, a=acct)
    saved(conn)
    return {"ok": True}


@router.post("/issues/{issueid}/resolve")
def resolve_issue(issueid: str, body: ResolveIn, request: Request,
                  user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """The problem has been dealt with, and here is what was done about it. Closing it takes the
    leg off Needs Attention, so what was done has to be written down - an issue closed with no
    account of it is the same as one nobody answered."""
    acct = user["accountid"]
    issue = _issue_in_context(conn, acct, issueid)
    if not issue:
        raise HTTPException(404, "No such issue")
    if body.kind not in WHAT_WAS_DONE and body.kind not in WAS_ACTUALLY_DONE:
        raise HTTPException(400, "Say what was done about it")
    # A claim about work is checked against the work. Refused here as well as hidden in the
    # screen, because a screen is not where a rule lives.
    if body.kind in WAS_ACTUALLY_DONE and body.kind not in _what_changed(conn, acct, issue):
        raise HTTPException(400, f"{WAS_ACTUALLY_DONE[body.kind]} - but that has not happened yet")
    note = (body.resolution or "").strip()
    # Everything else names itself. "Something else" names nothing, so it has to be written out
    # or the record says only that somebody pressed a button.
    if body.kind == "other" and not note:
        raise HTTPException(400, "Say what was done about it")
    now = utcnow()
    run(conn, """
        UPDATE tripissues SET resolvedon = :now, resolvedby = :by, resolutionkind = :k,
               resolution = :r,
               acknowledgedon = COALESCE(acknowledgedon, :now),
               acknowledgedby = COALESCE(acknowledgedby, :by)
        WHERE recordid = :i AND accountid = :a AND resolvedon IS NULL
    """, now=now, by=user["recordid"], k=body.kind, r=note[:600] or None, i=issueid, a=acct)
    log(conn, user, "issue-resolved", "trip", issue["tripid"],
        {"issueid": issueid, "kind": body.kind, "resolution": note[:600]}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.get("/dispatch/board")
def dispatch_board(day: date | None = None, state: str = "needsdriver", q: str | None = None,
                   page: int = 1, pagesize: int = 50, sort: str = "pickupat", dir: str = "asc",
                   user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """The day's work, one row per LEG.

    A leg, not a trip, because a leg is what a driver is given. A reservation out to a clinic and
    back is two pieces of work, often for two drivers, and a board that lists it once cannot say
    that the return is uncovered."""
    acct = user["accountid"]
    pagesize = max(1, min(pagesize, 200))
    # A pickup time is a WALL CLOCK time in the company's own zone - 2pm means 2pm in Florida,
    # whatever the server thinks the hour is. Comparing it to UTC_TIMESTAMP() made every trip
    # look four hours later than it was, so an afternoon pickup read as missed before lunch.
    here = localnow(user.get("timezone") or _account_zone(conn, acct))
    where = ["t.accountid = :a", "t.deleted IS NULL"]
    # From ninety minutes before today's close, a will-call the company is still responsible for and
    # nobody has collected needs its coverage recorded - who is on call for it, or who else took it.
    # Coverage Needed, under Needs Attention, until that is on the record.
    closes = _closes(conn, acct, here.date())
    closesoon = closes - PAST_CLOSING if closes else None
    params = {"a": acct, "here": here, "today": here.date(),
              "closesoon": closesoon or datetime.combine(here.date(), datetime.max.time())}
    if day:
        # A will-call waiting for the passenger's call has no pickup time, so it is on every day's
        # board until it is called or settled. One settled before the call - canceled - belongs to
        # the day it was settled, in the company's own clock (the stamps are UTC).
        # From its own trip day onward - never on a day before the trip it belongs to.
        where.append("""(DATE(l.pickupat) = :day
                         OR (l.pickupat IS NULL AND l.outcomestate IS NULL AND t.tripdate <= :day)
                         OR (l.pickupat IS NULL AND l.outcomestate IS NOT NULL
                             AND DATE(DATE_ADD(COALESCE(t.cancelledon,
                                                       (SELECT MAX(c.changedon) FROM tripchanges c WHERE c.legid = l.recordid),
                                                       l.added), INTERVAL :tzoff MINUTE)) = :day))""")
        params["day"] = day
        params["tzoff"] = round((here - utcnow()).total_seconds() / 60)
    if state == "needsdriver":
        where.append("l.driverid IS NULL AND l.executionstate = 'scheduled' AND l.outcomestate IS NULL")
    elif state == "assigned":
        where.append("l.driverid IS NOT NULL")
    elif state == "willcall":
        where.append("l.pickupat IS NULL AND l.outcomestate IS NULL")
    elif state == "attention":
        # Everything that will not happen on its own: nobody assigned to work that is due, a
        # driver taken off at short notice, a pickup time that has come and gone with the
        # driver never reporting that they set off, or a leg recorded as disputed and not settled.
        # The same legs the count on the button counts: a leg closed out - cancelled, a no-show,
        # not done - is finished business, whatever its pickup time says.
        # Or taken by the on-call driver after closing and not yet looked at, whatever came of it.
        where.append(f"""((l.selfassignedon IS NOT NULL AND l.afterhoursreviewedon IS NULL) OR (
            (l.outcomestate IS NULL OR l.outcomestate = 'disputed') AND (
            (l.driverid IS NULL AND l.pickupat IS NOT NULL
                 AND l.pickupat < :here + INTERVAL 2 HOUR
                 AND COALESCE(l.brokerstate, t.brokerstate) NOT IN ('offered', 'returnpending', 'returned'))
            OR t.dispatchstate = 'needsreassign'
            OR {tripcheck.STOPPED_LEG}
            OR (l.executionstate = 'scheduled' AND l.pickupat IS NOT NULL
                 AND l.pickupat < :here - INTERVAL COALESCE((SELECT ap.ontimeminutes FROM accountpayers ap
                      WHERE ap.accountid = t.accountid AND ap.payerid = t.brokerid), :grace) MINUTE)
            OR EXISTS (SELECT 1 FROM tripissues i3
                        WHERE i3.legid = l.recordid AND i3.resolvedon IS NULL)
            OR l.outcomestate = 'disputed'
            OR EXISTS (SELECT 1 FROM tripchanges c WHERE c.legid = l.recordid
                        AND c.driverid = l.driverid AND c.seenon IS NULL)
            OR (l.pickupat IS NULL AND l.brokerstate IS NULL AND t.cancelledon IS NULL
                 AND t.brokerstate NOT IN ('offered', 'returnpending', 'returned') AND t.tripdate = :today AND :here >= :closesoon
                 AND COALESCE(l.responsibility, 'provider') IN ('provider', 'unconfirmed')
                 AND NOT EXISTS (SELECT 1 FROM returncoverage rc WHERE rc.legid = l.recordid))
            -- Still waiting at a facility about to lock up: they could be left outside.
            OR (l.pickupat IS NULL AND l.brokerstate IS NULL AND t.cancelledon IS NULL AND t.tripdate = :today
                 AND t.brokerstate NOT IN ('offered', 'returnpending', 'returned')
                 AND COALESCE(l.responsibility, 'provider') IN ('provider', 'unconfirmed')
                 AND EXISTS (SELECT 1 FROM places p WHERE p.accountid = l.accountid AND p.deleted IS NULL
                              AND CONCAT_WS(', ', p.address, p.city, CONCAT_WS(' ', p.state, p.zip)) = l.pickupplace
                              AND TIMESTAMP(t.tripdate, p.closesat) - INTERVAL :facilitywarn MINUTE <= :here))
            -- A will-call well past its Ready About with no call recorded: somebody rings them.
            OR (l.pickupat IS NULL AND l.brokerstate IS NULL AND t.cancelledon IS NULL AND l.readyabout IS NOT NULL
                 AND t.brokerstate NOT IN ('offered', 'returnpending', 'returned') AND t.tripdate = :today
                 AND l.readyabout < :here - INTERVAL :overdue MINUTE)
            -- A will-call from an earlier day that nobody ever took: it has to be closed, not left.
            OR (l.pickupat IS NULL AND l.brokerstate IS NULL AND t.cancelledon IS NULL
                 AND t.brokerstate NOT IN ('offered', 'returnpending', 'returned') AND t.tripdate < :today)
        )))""")
        params["grace"] = LATE_AFTER
        params["overdue"] = CALL_OVERDUE
        params["facilitywarn"] = FACILITY_WARNING
    elif state == "incoming":
        where.append("t.brokerstate = 'offered'")
    elif state == "returning":
        # Still ours until the broker says otherwise, so it stays on the board rather than
        # disappearing the moment somebody pressed Return.
        where.append("COALESCE(l.brokerstate, t.brokerstate) = 'returnpending'")
    if q:
        where.append("(t.externalid LIKE CONCAT('%', :q, '%') OR t.passenger LIKE CONCAT('%', :q, '%'))")
        params["q"] = q
    clause = " AND ".join(where)
    order = BOARD_SORTS.get(sort, BOARD_SORTS["pickupat"]).replace(
        "{d}", "DESC" if str(dir).lower() == "desc" else "ASC")
    total = (row(conn, f"SELECT COUNT(*) AS n FROM triplegs l JOIN trips t ON t.recordid = l.tripid "
                       f"WHERE {clause}", **params) or {}).get("n", 0)
    items = rows(conn, f"""
        SELECT l.recordid AS legid, l.legnumber, l.pickupat, l.dropoffat, l.appointmentat,
               (SELECT MIN(e.happenedon) FROM tripevents e WHERE e.legid = l.recordid
                AND e.state = 'onboard') AS onboardat,
               l.pickuplat, l.pickuplng, l.dropofflat, l.dropofflng, l.pickupplace,
               l.dropoffplace, l.executionstate, l.outcomestate, l.driverid, l.vehicleid,
               {tripcheck.STOPPED_LEG} AS compliancestop,
               (SELECT e.blockers FROM tripeligibility e WHERE e.accountid = l.accountid AND e.legid = l.recordid
                ORDER BY e.evaluatedon DESC, e.decision = 'notqualified' DESC LIMIT 1) AS stopblockers,
               l.readyabout, l.returnplan, l.brokerstate IS NOT NULL AS legreturn, t.tripdate,
               l.selfassignedon, l.afterhoursreviewedon, l.responsibility, l.responsibilitynote,
               l.activationsource, l.activatedon, l.brokerreadyat, t.brokerid,
               (SELECT GROUP_CONCAT(CONCAT_WS('|', rc.kind, rc.person, COALESCE(rc.contact, ''), COALESCE(rc.until, ''))
                                    ORDER BY rc.person SEPARATOR '\n')
                  FROM returncoverage rc WHERE rc.legid = l.recordid
                   AND rc.recordedon = (SELECT MAX(x.recordedon) FROM returncoverage x WHERE x.legid = l.recordid)) AS coverage,
               (l.legnumber = 1 AND EXISTS (SELECT 1 FROM triplegs r WHERE r.tripid = l.tripid AND r.legnumber > 1
                    AND r.responsibility = 'unconfirmed' AND r.brokerstate IS NULL AND r.outcomestate IS NULL)) AS returnundecided,
               t.recordid AS tripid, t.externalid, t.passenger, t.servicelevel, t.critical,
               t.billedamount,
               COALESCE(l.brokerstate, t.brokerstate) AS brokerstate,
               (SELECT MIN(p.closesat) FROM places p WHERE p.accountid = l.accountid AND p.deleted IS NULL
                   AND CONCAT_WS(', ', p.address, p.city, CONCAT_WS(' ', p.state, p.zip)) = l.pickupplace) AS facilitycloses,
               -- The broker's confirmation number, once they have confirmed taking it back.
               (SELECT r.acknowledgedref FROM triprejections r WHERE r.tripid = t.recordid
                   AND (r.legid = l.recordid OR r.legid IS NULL) AND r.acknowledgedon IS NOT NULL
                 ORDER BY r.acknowledgedon DESC LIMIT 1) AS brokerref,
               t.dispatchstate, b.code AS broker, t.billingstatus, t.cancelledon IS NOT NULL AS cancelled,
               (SELECT c.reason FROM tripchanges c WHERE c.legid = l.recordid AND l.pickupat IS NULL
                ORDER BY c.changedon DESC LIMIT 1) AS lastcall,
               (SELECT MAX(c.changedon) FROM tripchanges c WHERE c.legid = l.recordid
                AND l.pickupat IS NULL) AS lastcallon,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername,
               d.phone AS driverphone,
               v.externalid AS vehiclename,
               i.recordid AS issueid, i.kind AS issuekind, i.note AS issuenote,
               i.raisedon AS issueraisedon, i.acknowledgedon AS issueseen,
               i.latitude AS issuelat, i.longitude AS issuelng
        FROM triplegs l
        JOIN trips t ON t.recordid = l.tripid
        LEFT JOIN payers b ON b.recordid = t.brokerid
        LEFT JOIN drivers d ON d.recordid = l.driverid
        LEFT JOIN vehicles v ON v.recordid = l.vehicleid
        -- The newest thing the driver has said is wrong and nobody has dealt with. A board that
        -- does not carry it is a board that lets a telephone call from the roadside go nowhere.
        LEFT JOIN tripissues i ON i.recordid = (
            SELECT i2.recordid FROM tripissues i2
             WHERE i2.legid = l.recordid AND i2.resolvedon IS NULL
             ORDER BY i2.raisedon DESC LIMIT 1)
        WHERE {clause}
        ORDER BY {order}, t.externalid, l.legnumber
        LIMIT :lim OFFSET :off
    """, **params, lim=pagesize, off=(max(1, page) - 1) * pagesize)
    # How much is on the attention board right now, whichever board is being looked at. Without
    # this a dispatcher watching "Needs a driver" has no way of learning that a driver has just
    # broken down, short of changing filter on the off-chance.
    attention = (row(conn, f"""
        SELECT COUNT(*) AS n FROM triplegs l JOIN trips t ON t.recordid = l.tripid
        WHERE t.accountid = :a AND t.deleted IS NULL AND (l.outcomestate = 'disputed' OR (
            l.outcomestate IS NULL AND (
            (l.driverid IS NULL AND l.pickupat IS NOT NULL
                 AND l.pickupat < :here + INTERVAL 2 HOUR
                 AND COALESCE(l.brokerstate, t.brokerstate) NOT IN ('offered', 'returnpending', 'returned'))
            OR t.dispatchstate = 'needsreassign'
            OR {tripcheck.STOPPED_LEG}
            OR (l.executionstate = 'scheduled' AND l.pickupat IS NOT NULL
                 AND l.pickupat < :here - INTERVAL COALESCE((SELECT ap.ontimeminutes FROM accountpayers ap
                      WHERE ap.accountid = t.accountid AND ap.payerid = t.brokerid), :grace) MINUTE)
            OR EXISTS (SELECT 1 FROM tripissues i3
                        WHERE i3.legid = l.recordid AND i3.resolvedon IS NULL)))
            OR EXISTS (SELECT 1 FROM tripchanges c WHERE c.legid = l.recordid
                        AND c.driverid = l.driverid AND c.seenon IS NULL))
    """, a=acct, here=here, grace=LATE_AFTER) or {}).get("n", 0)
    # The open problems themselves, not a count of them - and whatever board is being looked at,
    # because a problem that cannot be seen from here is exactly the one worth carrying. A number
    # says somebody is in trouble; only the record says who, what, and how long they have waited.
    problems = rows(conn, """
        SELECT i.recordid, i.kind, i.note, i.raisedon, i.acknowledgedon, i.latitude, i.longitude,
               i.legid, i.tripid, i.driverid, l.pickupat, t.externalid, t.passenger,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername,
               -- The van that was on the leg WHEN the fault was reported. Taking a vehicle off
               -- the road clears it from its legs, so reading the leg afterwards says there was
               -- never a vehicle - and the strip then offers to take nothing off the road.
               av.recordid AS vehicleid, av.externalid AS vehiclename
        FROM tripissues i
        JOIN trips t ON t.recordid = i.tripid AND t.deleted IS NULL
        LEFT JOIN triplegs l ON l.recordid = i.legid
        LEFT JOIN vehicles av ON av.recordid = COALESCE(
            (SELECT a2.vehicleid FROM tripassignments a2
              WHERE a2.legid = i.legid AND a2.assignedon <= i.raisedon
                AND (a2.endedon IS NULL OR a2.endedon >= i.raisedon)
              ORDER BY a2.assignedon DESC LIMIT 1), l.vehicleid)
        LEFT JOIN drivers d ON d.recordid = i.driverid
        WHERE i.accountid = :a AND i.resolvedon IS NULL
        ORDER BY i.raisedon
    """, a=acct)

    # Whether this company has any work at all, as against none matching today's filter. A board
    # that says "every leg has a driver" when there are no legs is telling a comforting lie to
    # somebody whose real problem is that nothing has been booked yet.
    anywork = (row(conn, """
        SELECT COUNT(*) AS n FROM triplegs l JOIN trips t ON t.recordid = l.tripid
        WHERE t.accountid = :a AND t.deleted IS NULL
    """, a=acct) or {}).get("n", 0)
    # Whether each one is slipping, worked out here rather than in the browser: "late" depends on
    # the clock, and a page left open overnight would otherwise still be showing this morning's
    # trips as fine.
    # The app's moments are instants (UTC); the board reads wall clock in the company's zone.
    shift_to_local = timedelta(minutes=round((here - utcnow()).total_seconds() / 60))
    # Each broker's will-call terms with this company (Payers, Will-Call Rules), for the deadlines.
    terms = {r["payerid"]: r for r in rows(conn, "SELECT payerid, pickuplimit, clockstarts, ontimeminutes FROM accountpayers "
                                                  "WHERE accountid = :a", a=acct)}
    seen = dispatch._last_seen(conn, acct) if any(
        i["executionstate"] in ("enroute", "arrived", "onboard") for i in items) else {}
    for i in items:
        a, b = i.pop("pickuplat"), i.pop("pickuplng")
        c, d = i.pop("dropofflat"), i.pop("dropofflng")
        pickup = (float(a), float(b)) if None not in (a, b) else None
        dropoff = (float(c), float(d)) if None not in (c, d) else None
        # Where it sits on the calendar, by what the driver's app said: from the moment the
        # passenger was aboard (the booked pickup until then) to the moment they arrived.
        onboard = i.pop("onboardat")
        i["pickedupat"] = onboard + shift_to_local if onboard else None
        # Under way: how long is left, from where the driver last reported, and so when it should
        # be over - to the drop-off once aboard, by way of the pickup before.
        i["eta"] = None
        where = seen.get(i["driverid"]) if i["driverid"] else None
        if (i["executionstate"] in ("enroute", "arrived", "onboard") and not i["outcomestate"]
                and where and where["fresh"] and dropoff):
            now_at = (where["lat"], where["lng"])
            left = (routing.drive(now_at, dropoff)["minutes"] if i["executionstate"] == "onboard" or not pickup
                    else routing.drive(now_at, pickup)["minutes"] + routing.drive(pickup, dropoff)["minutes"])
            i["eta"] = {"minutes": left, "at": here + timedelta(minutes=left)}
        # When it is expected to be over: done, when it was; under way, the estimate; else the
        # appointment it is for; else the pickup and the drive between its two addresses.
        i["expectedend"] = i["dropoffat"] or (i["eta"] or {}).get("at") or i["appointmentat"]
        if not i["expectedend"] and i["pickupat"] and pickup and dropoff:
            road = dispatch._miles(pickup, dropoff) * routing.ROAD_FACTOR
            i["expectedend"] = i["pickupat"] + timedelta(minutes=max(15, round(road / routing.TOWN_MPH * 60)))
        i["late"] = None
        if i["executionstate"] == "scheduled" and i["pickupat"] and not i["outcomestate"]:
            over = (here - i["pickupat"]).total_seconds() / 60
            if over > MISSED_AFTER:
                i["late"] = "missed"
            # Late by the broker's own on-time window where it sets one.
            elif over > ((terms.get(i["brokerid"]) or {}).get("ontimeminutes") or LATE_AFTER):
                i["late"] = "late"
        i["needsdriver"] = i["driverid"] is None and not i["outcomestate"]
        # Why it is on Needs Attention when nothing above has said so, in the same terms the
        # board selects it by - so a row there never reads "Scheduled" and leaves the dispatcher
        # to work out what is wrong with it.
        i["attention"] = None
        # A will-call waiting at a place within the hour of closing, or already closed.
        i["facilitycloses"] = (datetime.combine(i["tripdate"], plan.as_time(i["facilitycloses"]))
                               if i["facilitycloses"] is not None else None)
        i["closingsoon"] = bool(i["facilitycloses"] and not i["pickupat"] and not i["outcomestate"]
                                and not i["cancelled"] and i["brokerstate"] not in HANDED_BACK
                                and i["tripdate"] == here.date()
                                and here >= i["facilitycloses"] - timedelta(minutes=FACILITY_WARNING))
        if not i["outcomestate"] and not i["late"]:
            if i["dispatchstate"] == "needsreassign":
                i["attention"] = "reassign"
            # Asked back from the broker: waiting on them, not on a driver.
            elif (i["needsdriver"] and i["pickupat"] and i["pickupat"] < here + timedelta(hours=2)
                  and i["brokerstate"] not in HANDED_BACK):
                i["attention"] = "nodriver"
            elif (not i["pickupat"] and i["brokerstate"] not in HANDED_BACK and not i["cancelled"] and closesoon
                  and i["tripdate"] == here.date() and here >= closesoon and not i["coverage"]
                  and (i["responsibility"] or "provider") in ("provider", "unconfirmed")):
                i["attention"] = "coverage"
            elif i["closingsoon"] and (i["responsibility"] or "provider") in ("provider", "unconfirmed"):
                i["attention"] = "facilityclosing"
            elif (not i["pickupat"] and i["brokerstate"] not in HANDED_BACK and not i["cancelled"] and i["readyabout"]
                  and i["tripdate"] == here.date() and i["readyabout"] < here - timedelta(minutes=CALL_OVERDUE)):
                i["attention"] = "calloverdue"
            elif not i["pickupat"] and i["brokerstate"] not in HANDED_BACK and not i["cancelled"] and i["tripdate"] < here.date():
                i["attention"] = "nevercalled"
        # On a trip that may not run as assigned: ahead of everything else said about it.
        said = json.loads(i.pop("stopblockers") or "[]")
        i["stopwhy"] = next((b.get("reason") or b.get("name") for b in said if b.get("enforceable")), None)
        if i["compliancestop"] and not i["outcomestate"]:
            i["attention"] = "compliancestop"
        # Taken by the on-call driver after closing: the office's to look at in the morning.
        i["afterhours"] = bool(i["selfassignedon"] and not i["afterhoursreviewedon"])
        if i["coverage"]:
            people = [(p.split("|") + ["", "", "", ""])[:4] for p in i["coverage"].split("\n")]
            i["coverage"] = {"kind": people[0][0], "people": [
                {"person": person, "contact": contact or None, "until": until or None}
                for _, person, contact, until in people]}
        # A will-call activated for a broker with a pickup limit: when it has to be collected by,
        # from the passenger's call if that is when the broker's clock starts and we were told it.
        i["deadline"] = None
        rule = terms.get(i["brokerid"]) if i["brokerid"] else None
        if (rule and rule["pickuplimit"] and i["activatedon"] and i["legnumber"] > 1
                and i["executionstate"] in ("scheduled", "enroute", "arrived") and not i["outcomestate"]):
            start = (i["brokerreadyat"] if rule["clockstarts"] == "passenger" and i["brokerreadyat"]
                     else i["activatedon"] + (here - utcnow()))
            i["deadline"] = start + timedelta(minutes=rule["pickuplimit"])
        i["detail"] = _what_went_wrong(i, here)
        # A change the driver on the leg has not read. Said before anything else on the row: with
        # the passenger aboard it is a telephone call, not a note.
        i["unseen"] = None
        told = row(conn, """
            SELECT changedon, changes FROM tripchanges
            WHERE accountid = :a AND legid = :l AND driverid = :d AND seenon IS NULL
            ORDER BY changedon DESC LIMIT 1
        """, a=acct, l=i["legid"], d=i["driverid"]) if i["driverid"] else None
        # Only the driver on the leg now. A notice for one taken off it went with them: whoever
        # took over was given the trip as it reads today.
        if told:
            what = ", ".join(c["field"] for c in json.loads(told["changes"] or "[]")) or "The trip"
            when = told["changedon"].replace(tzinfo=timezone.utc).astimezone(
                ZoneInfo(user.get("timezone") or _account_zone(conn, acct))).strftime("%-I:%M %p")
            who = i["drivername"] or "The driver"
            call = f" Call {i['driverphone']}." if i["driverphone"] else " Call them."
            i["unseen"] = {"changedon": told["changedon"], "what": what}
            i["detail"] = (f"CALL THE DRIVER NOW: {what} changed at {when} with the passenger aboard. "
                           f"{who} has not seen it.{call}" if i["executionstate"] == "onboard" else
                           f"{what} changed at {when}. {who} has not seen it yet.{call}")
        i["dispute"] = None
        if i["outcomestate"] == "disputed":
            i["detail"] = _dispute(conn, acct, i)
            held = _open_dispute(conn, acct, i["legid"])
            i["dispute"] = held and {"raisedon": held["raisedon"], "reason": held["reason"],
                                     "raisedby": held["raisedbyname"]}
    return {"items": items, "total": total, "page": page, "pagesize": pagesize,
            "anywork": bool(anywork), "attention": attention, "problems": problems,
            "services": {k: v["label"] for k, v in dispatch.SERVICE.items()},
            # The words a dispatcher may use, from the one place that decides what the server
            # will accept - so a reason the screen offers is never one the server refuses.
            "returnreasons": RETURN_REASONS, "cancelreasons": CANCEL_REASONS, "notneeded": NOT_NEEDED,
            "whathappened": WHAT_HAPPENED, "issuekinds": driverapp.ISSUES,
            "whatwasdone": {**WAS_ACTUALLY_DONE, **WHAT_WAS_DONE}}


def _open_dispute(conn: Connection, acct: str, legid: str) -> dict | None:
    """The dispute standing against a leg, with who raised it."""
    return row(conn, """
        SELECT d.recordid, d.raisedon, d.reason, u.name AS raisedbyname
        FROM tripdisputes d LEFT JOIN users u ON u.recordid = d.raisedby
        WHERE d.accountid = :a AND d.legid = :l AND d.settledon IS NULL
        ORDER BY d.raisedon DESC LIMIT 1
    """, a=acct, l=legid)


def _settle_dispute(conn: Connection, acct: str, legid: str, settlement: str, note: str | None,
                    userid: str, now: datetime) -> None:
    run(conn, """
        UPDATE tripdisputes SET settledon = :now, settledby = :by, settlement = :s, settlenote = :n
        WHERE accountid = :a AND legid = :l AND settledon IS NULL
    """, now=now, by=userid, s=settlement, n=(note or "")[:2000] or None, a=acct, l=legid)


def _dispute(conn: Connection, acct: str, leg: dict) -> str:
    """Who disputed it and why, and that it stays open until somebody settles it."""
    said = _open_dispute(conn, acct, leg["legid"])
    who = f" by {said['raisedbyname']}" if said and said.get("raisedbyname") else ""
    why = f": {said['reason']}" if said and said.get("reason") else ". No reason was recorded"
    return f"Disputed{who}{why}. It stays open until it is settled."


def _what_went_wrong(leg: dict, here: datetime) -> str | None:
    """The sentence behind a flagged row, in the room the board has beside it. The Status column
    says which kind of trouble in a word; this says what actually happened, so nobody has to
    open the trip to learn that Carl never set off for an eleven o'clock pickup."""
    at = leg["pickupat"].strftime("%-I:%M %p") if leg["pickupat"] else None
    who = leg["drivername"] or None
    if leg["issueid"]:
        said = driverapp.ISSUES.get(leg["issuekind"], "A problem")
        note = f" - {leg['issuenote']}" if leg["issuenote"] else ""
        seen = "" if leg["issueseen"] else " Nobody in the office has seen it yet."
        return f"{who or 'The driver'} reported: {said}{note}.{seen}"
    if leg["outcomestate"]:
        return None
    if leg["attention"] == "compliancestop":
        why = leg.get("stopwhy") or "A driving record was read as disqualifying."
        return f"{who or 'The driver'} may not run this trip: {why} Change the driver or vehicle."
    if leg["late"]:
        minutes = int((here - leg["pickupat"]).total_seconds() // 60)
        gone = f"{minutes} minutes ago" if minutes < 120 else f"{minutes // 60} hours ago"
        if not who:
            return f"Pickup was {at}, {gone}, and nobody is on it."
        return f"Pickup was {at}, {gone}. {who} has not reported setting off."
    if leg["attention"] == "nodriver":
        minutes = max(0, int((leg["pickupat"] - here).total_seconds() // 60))
        return f"Pickup at {at}, {minutes} minutes from now, and nobody is on it."
    if leg["attention"] == "reassign":
        return "The driver was taken off this trip and nobody has been put on it."
    return None


# A pickup time that has come and gone with the driver never reporting that they set off. Ten
# minutes is a courtesy; an hour is not a delay, it is a trip nobody drove, and the two want
# different words because they want different actions.
LATE_AFTER = 10       # minutes past the pickup before it is worth looking at
MISSED_AFTER = 60     # past which nobody is pretending it is running late


# What the board may sort on. The leg number breaks ties so an outbound always reads above its
# return, whatever else the dispatcher has sorted by.
BOARD_SORTS = {
    "pickupat": "l.pickupat IS NULL, l.pickupat {d}",
    "passenger": "t.passenger {d}",
    "externalid": "t.externalid {d}",
    "drivername": "l.driverid IS NULL, drivername {d}",
    "servicelevel": "t.servicelevel {d}",
    "executionstate": "l.executionstate {d}",
}


@router.get("/legs/{legid}/candidates")
def leg_candidates(legid: str, vehicleid: str | None = None, user: dict = Depends(current_user),
                   conn: Connection = Depends(get_conn)):
    """Who may take this leg, who may not, and why - in the words of the engine that will later be
    asked to prove the trip was compliant. With `vehicleid`, the drivers judged in that vehicle:
    whether somebody needs a commercial licence depends on what they would be driving."""
    said = dispatch.for_leg(conn, user["accountid"], legid, vehicle=vehicleid)
    if not said:
        raise HTTPException(404, "No such leg")
    said["mayoverride"] = _supervisor(conn, user)
    # Who may accept a restricted driving record for this trip.
    said["mayclear"] = user.get("role") in ("owner", "admin")
    return said


@router.post("/legs/{legid}/assign")
def assign_leg(legid: str, body: AssignIn, request: Request, user: dict = Depends(editor),
               conn: Connection = Depends(get_conn)):
    """Put a driver and a vehicle on one leg.

    The candidate list is computed again here rather than trusted from the browser. A screen can be
    left open while a licence expires, and the one thing this endpoint must never do is file an
    assignment that the engine would not have offered a moment earlier."""
    acct = user["accountid"]
    # The driver judged in the vehicle they are being given, and only that driver.
    said = dispatch.for_leg(conn, acct, legid, only={body.driverid} if body.driverid else None,
                            vehicle_of={body.driverid: body.vehicleid} if body.driverid and body.vehicleid else None)
    if not said:
        raise HTTPException(404, "No such leg")
    # A will-call is not scheduled until the passenger calls: no time, so no driver yet. Passenger
    # Called gives it its time, and then it is assigned like any other leg.
    if body.driverid and not said["leg"]["pickupat"]:
        raise HTTPException(409, "A will-call gets its driver once the passenger calls and it has a pickup time.")
    gone = row(conn, "SELECT COALESCE(l.brokerstate, t.brokerstate) AS brokerstate FROM triplegs l "
                     "JOIN trips t ON t.recordid = l.tripid WHERE l.recordid = :l", l=legid) or {}
    if body.driverid and gone.get("brokerstate") in ("returnpending", "returned"):
        raise HTTPException(409, "This trip has been sent back to the broker, so it cannot be given a driver.")
    # The trip there is not dispatched while nobody has decided who brings the passenger home.
    first = row(conn, "SELECT legnumber FROM triplegs WHERE recordid = :l", l=legid) or {}
    undecided = return_undecided(conn, acct, said["leg"]["tripid"]) if first.get("legnumber") == 1 else None
    if body.driverid and undecided:
        raise HTTPException(409, _undecided_said(undecided))
    chosen_driver = next((d for d in said["drivers"] if d["driverid"] == body.driverid), None)
    chosen_vehicle = next((v for v in said["vehicles"] if v["vehicleid"] == body.vehicleid), None)
    if body.driverid and not chosen_driver:
        raise HTTPException(404, "No such driver on this account")
    if body.vehicleid and not chosen_vehicle:
        raise HTTPException(404, "No such vehicle on this account")

    # A hard block has no override, by anybody. Not a disabled control, not a confirmation: the
    # answer is no, and the reason is the one the engine gave.
    # Said with who it is about, and for which trip day: on a board of a dozen drivers "On file, but
    # it ran out" names nobody.
    for who in (chosen_driver, chosen_vehicle):
        if who and who["blocked"]:
            name = (who.get("name") or who.get("externalid") or "").title() if who is chosen_driver \
                else who.get("externalid") or who.get("name") or ""
            raise HTTPException(409, f"{name} cannot take this trip"
                                     + (f" on {said['leg']['pickupat']:%m/%d/%Y}" if said['leg'].get("pickupat") else "")
                                     + f": {who['blocked'][0]}")

    warnings = (chosen_driver or {}).get("warnings", []) + (chosen_vehicle or {}).get("warnings", [])
    # A restricted driving record is accepted for a trip by an owner or admin only; every other
    # warning by a supervisor. Either way with the reason, kept on the assignment.
    holds = (chosen_driver or {}).get("holds", [])
    others = [w for w in warnings if w not in holds]
    overriding = bool(warnings)
    if holds and user.get("role") not in ("owner", "admin"):
        raise HTTPException(403, f"{holds[0]} - only an owner or admin can accept it for this trip.")
    if others and not _supervisor(conn, user):
        raise HTTPException(403, f"{others[0]} - a supervisor has to accept that.")
    if overriding and not (body.overridereason or "").strip():
        raise HTTPException(400, "Say why this is being accepted.")

    now = utcnow()
    # The one in force is ended rather than deleted, and the new one is written beside it. A
    # dispatcher changing their mind twice leaves three rows, which is the point.
    run(conn, """
        UPDATE tripassignments SET endedon = :now, endedby = :by, endreason = 'reassigned'
        WHERE accountid = :a AND legid = :l AND endedon IS NULL
    """, now=now, by=user["recordid"], a=acct, l=legid)
    run(conn, """
        INSERT INTO tripassignments (recordid, accountid, legid, driverid, vehicleid, assignedon,
                                     assignedby, override, overridereason)
        VALUES (:id, :a, :l, :d, :v, :now, :by, :o, :why)
    """, id=newid(), a=acct, l=legid, d=body.driverid, v=body.vehicleid, now=now,
        by=user["recordid"], o=1 if overriding else 0,
        why=(body.overridereason or "").strip()[:400] or None)
    run(conn, """
        UPDATE triplegs SET driverid = :d, vehicleid = :v
        WHERE recordid = :l AND accountid = :a
    """, d=body.driverid, v=body.vehicleid, l=legid, a=acct)
    _shadow_check(conn, acct, body.driverid, body.vehicleid, legid, user["recordid"])
    # Told by text: the driver now on it, and the one it was taken from.
    was, ref, at = said["leg"]["driverid"], said["leg"]["externalid"], said["leg"]["pickupat"]
    if body.driverid and body.driverid != was:
        sms.tell(conn, acct, body.driverid, "assigned",
                 f"New trip {ref}, pickup {sms.when(at)}. Open the TripProof app for the details.",
                 said["leg"]["tripid"], legid)
    if was and was != body.driverid:
        sms.tell(conn, acct, was, "removed",
                 f"Trip {ref}, pickup {sms.when(at)}, is no longer yours. Open the app.",
                 said["leg"]["tripid"], legid)

    tripid = said["leg"]["tripid"]
    _settle_dispatch_state(conn, acct, tripid)
    # Re-read the trip against the engine now, so the grid tells the truth the moment somebody
    # acts rather than at the next nightly run.
    evaluate(conn, acct, tripids=[tripid], userid=user["recordid"], reason="assignment")
    log(conn, user, "trip-assigned", "trip", tripid,
        {"legid": legid, "driverid": body.driverid, "vehicleid": body.vehicleid,
         "override": overriding, "why": body.overridereason,
         "accepted": warnings or None}, ip=client_ip(request))
    saved(conn)
    return {"ok": True, "override": overriding}


class PlaceIn(BaseModel):
    legid: str
    driverid: str
    overridereason: str | None = None


@router.post("/dispatch/place")
def place_leg(body: PlaceIn, request: Request, user: dict = Depends(editor),
              conn: Connection = Depends(get_conn)):
    """A trip dropped on a driver's column of the day's calendar: that driver, in the vehicle they
    are assigned that day. The assignment itself passes the same gate as any other."""
    acct = user["accountid"]
    leg = row(conn, """
        SELECT l.pickupat, t.tripdate FROM triplegs l JOIN trips t ON t.recordid = l.tripid
        WHERE l.recordid = :l AND l.accountid = :a
    """, l=body.legid, a=acct)
    if not leg:
        raise HTTPException(404, "No such leg")
    day = leg["pickupat"].date() if leg["pickupat"] else leg["tripdate"]
    on = dayplan.day_vehicle(conn, acct, body.driverid, day, leg["pickupat"])
    if not on:
        who = row(conn, "SELECT TRIM(CONCAT(firstname, ' ', lastname)) AS n FROM drivers "
                        "WHERE recordid = :d AND accountid = :a", d=body.driverid, a=acct)
        raise HTTPException(409, f"{(who or {}).get('n', 'This driver').title()} has no vehicle assigned "
                                 f"on {day:%m/%d/%Y}. Vehicle Assignments gives them one.")
    return assign_leg(body.legid, AssignIn(driverid=body.driverid, vehicleid=on["vehicleid"],
                                           overridereason=body.overridereason), request, user, conn)


class DayIn(BaseModel):
    day: date


class AutoPlanIn(BaseModel):
    day: date
    legids: list[str] | None = None   # the ticked trips; none given is every unassigned trip


@router.post("/dispatch/autoplan")
def auto_plan(body: AutoPlanIn, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """A driver for each of the chosen unassigned trips, with the reasons. Nothing is saved."""
    if body.legids is not None and not body.legids:
        raise HTTPException(400, "Tick the trips to assign")
    only = set(body.legids) if body.legids is not None else None
    return {"proposal": dayplan.propose(conn, user["accountid"], body.day, only)}


class PlannedLeg(BaseModel):
    legid: str
    driverid: str
    vehicleid: str


class PlanSaveIn(BaseModel):
    items: list[PlannedLeg]


@router.post("/dispatch/autoplan/save")
def save_auto_plan(body: PlanSaveIn, request: Request, user: dict = Depends(editor),
                   conn: Connection = Depends(get_conn)):
    """Each proposed assignment through the ordinary gate, one by one. One the gate now refuses -
    something changed since the proposal - is left unassigned and said; the rest are kept."""
    done, refused = 0, []
    for i in body.items:
        try:
            assign_leg(i.legid, AssignIn(driverid=i.driverid, vehicleid=i.vehicleid), request, user, conn)
            done += 1
        except HTTPException as e:
            ext = row(conn, "SELECT t.externalid FROM triplegs l JOIN trips t ON t.recordid = l.tripid "
                            "WHERE l.recordid = :l", l=i.legid)
            refused.append(f"{(ext or {}).get('externalid', 'A trip')}: {e.detail}")
    return {"saved": done, "refused": refused}


@router.delete("/legs/{legid}/assign")
def unassign_leg(legid: str, body: UnassignIn, request: Request, user: dict = Depends(editor),
                 conn: Connection = Depends(get_conn)):
    """Take the driver and vehicle off a leg, saying which of the four things happened."""
    acct = user["accountid"]
    leg = row(conn, """
        SELECT l.recordid, l.tripid, l.driverid, l.pickupat, t.externalid FROM triplegs l
        JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        WHERE l.recordid = :id AND l.accountid = :a
    """, id=legid, a=acct)
    if not leg:
        raise HTTPException(404, "No such leg")
    if body.endreason not in END_REASONS:
        raise HTTPException(400, "Say why it is coming off this driver")
    sms.tell(conn, acct, leg["driverid"], "removed",
             f"Trip {leg['externalid']}, pickup {sms.when(leg['pickupat'])}, is no longer yours. Open the app.",
             leg["tripid"], legid)
    run(conn, """
        UPDATE tripassignments SET endedon = :now, endedby = :by, endreason = :r
        WHERE accountid = :a AND legid = :l AND endedon IS NULL
    """, now=utcnow(), by=user["recordid"], r=body.endreason, a=acct, l=legid)
    run(conn, "UPDATE triplegs SET driverid = NULL, vehicleid = NULL "
              "WHERE recordid = :l AND accountid = :a", l=legid, a=acct)
    _settle_dispatch_state(conn, acct, leg["tripid"])
    # A driver dropping out of tomorrow is a gap to fill at leisure. A driver dropping out of a
    # pickup in forty minutes is somebody standing on a kerb, so the trip says so and surfaces on
    # the board under Needs Attention rather than quietly rejoining the unassigned pile.
    soon = row(conn, """
        SELECT 1 AS x FROM triplegs WHERE recordid = :l AND accountid = :a
          AND pickupat IS NOT NULL AND pickupat < :here + INTERVAL 2 HOUR
    """, l=legid, a=acct, here=localnow(user.get("timezone") or _account_zone(conn, acct)))
    if soon and body.endreason in ("driver-declined", "reassigned"):
        run(conn, "UPDATE trips SET dispatchstate = 'needsreassign', updated = :now "
                  "WHERE recordid = :t AND accountid = :a", now=utcnow(), t=leg["tripid"], a=acct)
    evaluate(conn, acct, tripids=[leg["tripid"]], userid=user["recordid"], reason="assignment")
    log(conn, user, "trip-unassigned", "trip", leg["tripid"],
        {"legid": legid, "endreason": body.endreason}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


# What a dispatcher may say when handing a trip back. Written down rather than typed, because a
# broker asks why in its own vocabulary and a free-text box cannot be reported on.
RETURN_REASONS = {
    "drivershortage": "Driver shortage", "vehicleunavailable": "Vehicle unavailable",
    "outsidearea": "Outside the service area", "outsidehours": "Outside operating hours",
    "wronglevel": "Wrong level of service", "capacity": "Capacity exceeded", "other": "Other",
}


class ReturnIn(BaseModel):
    reason: str
    note: str | None = None


class AcknowledgedIn(BaseModel):
    ref: str | None = None
    sentby: str = "portal"


class LegStateIn(BaseModel):
    executionstate: str | None = None
    outcomestate: str | None = None


@router.post("/trips/{tripid}/accept")
def accept_trip(tripid: str, request: Request, user: dict = Depends(editor),
                conn: Connection = Depends(get_conn)):
    """Take on a trip a broker has offered."""
    acct = user["accountid"]
    held = row(conn, "SELECT recordid, brokerstate FROM trips WHERE recordid = :t AND accountid = :a "
                     "AND deleted IS NULL", t=tripid, a=acct)
    if not held:
        raise HTTPException(404, "No such trip")
    if held["brokerstate"] != "offered":
        raise HTTPException(409, "That trip is not an open offer")
    run(conn, "UPDATE trips SET brokerstate = 'accepted', confirmedon = :now, updated = :now WHERE recordid = :t",
        now=utcnow(), t=tripid)
    log(conn, user, "trip-accepted", "trip", tripid, {}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


def _within_notice(conn: Connection, acct: str, brokerid: str, pickups: list, note: str | None) -> None:
    """Inside the notice a broker asks for to take a trip back, it goes back only with who there agreed."""
    notice = row(conn, "SELECT ap.returnnoticehours AS h, p.name FROM payers p LEFT JOIN accountpayers ap "
                       "ON ap.payerid = p.recordid AND ap.accountid = :a WHERE p.recordid = :b", a=acct, b=brokerid) or {}
    first = min((p for p in pickups if p), default=None)
    if notice.get("h") and first and first - localnow(dispatch.zone(conn, acct)) < timedelta(hours=notice["h"]) \
            and not (note or "").strip():
        raise HTTPException(400, f"{notice['name']} asks for {notice['h']} hours' notice to take a trip back, and this one "
                                 f"picks up at {first:%-I:%M %p} on {first:%m/%d}. Say who at {notice['name']} agreed to take it.")


@router.post("/trips/{tripid}/return")
def return_trip(tripid: str, body: ReturnIn, request: Request, user: dict = Depends(editor),
                conn: Connection = Depends(get_conn)):
    """Hand a trip back to the broker it came from.

    The trip is NOT deleted and NOT detached. It goes to `returnpending` and stays the company's
    problem - still on the board, still counted as uncovered - until the broker says they have it.
    A rejection nobody acknowledged is a trip that simply does not get driven, and the only thing
    worse than losing it is believing it was handled."""
    acct = user["accountid"]
    held = row(conn, "SELECT recordid, externalid, brokerid, brokerstate, cancelledon FROM trips "
                     "WHERE recordid = :t AND accountid = :a AND deleted IS NULL", t=tripid, a=acct)
    if not held:
        raise HTTPException(404, "No such trip")
    if not held["brokerid"]:
        raise HTTPException(409, "This trip did not come from a broker, so there is nobody to "
                                 "return it to. Cancel it instead.")
    if held["cancelledon"]:
        raise HTTPException(409, "This trip is canceled. There is nothing to return.")
    if held["brokerstate"] in ("returnpending", "returned"):
        raise HTTPException(409, "This trip has already been sent back to the broker.")
    legs = rows(conn, "SELECT recordid, driverid, pickupat, executionstate, outcomestate FROM triplegs "
                      "WHERE tripid = :t AND accountid = :a", t=tripid, a=acct)
    if any(l["executionstate"] != "scheduled" or l["outcomestate"] for l in legs):
        raise HTTPException(409, "This trip has already started or been closed, so it can no longer "
                                 "be returned to the broker.")
    if body.reason not in RETURN_REASONS:
        raise HTTPException(400, "Say why it is going back")
    _within_notice(conn, acct, held["brokerid"], [l["pickupat"] for l in legs], body.note)
    # Nobody drives a trip that is going back: whoever was on it comes off, and is told.
    for l in legs:
        if not l["driverid"]:
            continue
        run(conn, """
            UPDATE tripassignments SET endedon = :now, endedby = :by, endreason = 'returned'
            WHERE accountid = :a AND legid = :l AND endedon IS NULL
        """, now=utcnow(), by=user["recordid"], a=acct, l=l["recordid"])
        run(conn, "UPDATE triplegs SET driverid = NULL, vehicleid = NULL WHERE recordid = :l AND accountid = :a",
            l=l["recordid"], a=acct)
        sms.tell(conn, acct, l["driverid"], "removed",
                 f"Trip {held['externalid']}, pickup {sms.when(l['pickupat'])}, is no longer yours. Open the app.",
                 tripid, l["recordid"])
    run(conn, """
        INSERT INTO triprejections (recordid, accountid, tripid, reason, note, requestedon,
                                    requestedby)
        VALUES (:id, :a, :t, :r, :n, :now, :by)
    """, id=newid(), a=acct, t=tripid, r=body.reason, n=(body.note or "").strip()[:600] or None,
        now=utcnow(), by=user["recordid"])
    run(conn, "UPDATE trips SET brokerstate = 'returnpending', updated = :now WHERE recordid = :t",
        now=utcnow(), t=tripid)
    log(conn, user, "trip-returned", "trip", tripid,
        {"reason": body.reason, "note": body.note}, ip=client_ip(request))
    saved(conn)
    return {"ok": True, "state": "returnpending"}


@router.post("/trips/{tripid}/return/acknowledged")
def return_acknowledged(tripid: str, body: AcknowledgedIn, request: Request,
                        user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """The broker has confirmed they have it back. Only this closes the loop."""
    acct = user["accountid"]
    pending = row(conn, """
        SELECT recordid FROM triprejections
        WHERE accountid = :a AND tripid = :t AND legid IS NULL AND acknowledgedon IS NULL
        ORDER BY requestedon DESC LIMIT 1
    """, a=acct, t=tripid)
    if not pending:
        raise HTTPException(404, "Nothing is waiting to be acknowledged on that trip")
    now = utcnow()
    run(conn, """
        UPDATE triprejections SET acknowledgedon = :now, acknowledgedref = :ref,
               senton = COALESCE(senton, :now), sentby = COALESCE(sentby, :how)
        WHERE recordid = :id
    """, now=now, ref=(body.ref or "").strip()[:64] or None, how=body.sentby[:16], id=pending["recordid"])
    run(conn, "UPDATE trips SET brokerstate = 'returned', updated = :now WHERE recordid = :t "
              "AND accountid = :a", now=now, t=tripid, a=acct)
    log(conn, user, "trip-return-acknowledged", "trip", tripid, {"ref": body.ref},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True, "state": "returned"}


@router.post("/legs/{legid}/return")
def return_leg(legid: str, body: ReturnIn, request: Request, user: dict = Depends(editor),
               conn: Connection = Depends(get_conn)):
    """Hand one leg back to the broker - the ride home we cannot cover - and keep the rest of the
    trip. Ours, on the board, until the broker confirms they have it."""
    acct = user["accountid"]
    leg = row(conn, "SELECT recordid, tripid, driverid, pickupat, executionstate, outcomestate, brokerstate "
                    "FROM triplegs WHERE recordid = :l AND accountid = :a", l=legid, a=acct)
    if not leg:
        raise HTTPException(404, "No such leg")
    trip = row(conn, "SELECT recordid, externalid, brokerid, brokerstate, cancelledon FROM trips "
                     "WHERE recordid = :t AND accountid = :a AND deleted IS NULL", t=leg["tripid"], a=acct)
    if not trip or not trip["brokerid"]:
        raise HTTPException(409, "This trip did not come from a broker, so there is nobody to return it to.")
    if trip["cancelledon"]:
        raise HTTPException(409, "This trip is canceled. There is nothing to return.")
    if trip["brokerstate"] in ("returnpending", "returned") or leg["brokerstate"]:
        raise HTTPException(409, "This has already been sent back to the broker.")
    if leg["executionstate"] != "scheduled" or leg["outcomestate"]:
        raise HTTPException(409, "This leg has already started or been closed, so it can no longer be returned.")
    if body.reason not in RETURN_REASONS:
        raise HTTPException(400, "Say why it is going back")
    _within_notice(conn, acct, trip["brokerid"], [leg["pickupat"]], body.note)
    _hand_back_leg(conn, acct, user, trip, leg, body.reason, body.note)
    log(conn, user, "leg-returned", "trip", trip["recordid"],
        {"leg": legid, "reason": body.reason, "note": body.note}, ip=client_ip(request))
    saved(conn)
    return {"ok": True, "state": "returnpending"}


@router.post("/legs/{legid}/return/acknowledged")
def leg_return_acknowledged(legid: str, body: AcknowledgedIn, request: Request,
                            user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """The broker has confirmed they are bringing the passenger home. Only this closes the leg."""
    acct = user["accountid"]
    pending = row(conn, """
        SELECT recordid, tripid FROM triprejections
        WHERE accountid = :a AND legid = :l AND acknowledgedon IS NULL
        ORDER BY requestedon DESC LIMIT 1
    """, a=acct, l=legid)
    if not pending:
        raise HTTPException(404, "Nothing is waiting to be acknowledged on that leg")
    now = utcnow()
    run(conn, """
        UPDATE triprejections SET acknowledgedon = :now, acknowledgedref = :ref,
               senton = COALESCE(senton, :now), sentby = COALESCE(sentby, :how)
        WHERE recordid = :id
    """, now=now, ref=(body.ref or "").strip()[:64] or None, how=body.sentby[:16], id=pending["recordid"])
    run(conn, "UPDATE triplegs SET brokerstate = 'returned' WHERE recordid = :l AND accountid = :a", l=legid, a=acct)
    log(conn, user, "leg-return-acknowledged", "trip", pending["tripid"], {"leg": legid, "ref": body.ref},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True, "state": "returned"}


class OnCallIn(BaseModel):
    person: str
    contact: str | None = None        # how they are reached
    until: datetime | None = None     # the end of their cover


class CoverageIn(BaseModel):
    kind: str                         # oncall | other
    person: str | None = None         # other: the provider that took it
    contact: str | None = None        # other: the provider's confirmation
    people: list[OnCallIn] = []       # oncall: everybody on call for it


@router.post("/legs/{legid}/coverage")
def record_coverage(legid: str, body: CoverageIn, request: Request, user: dict = Depends(editor),
                    conn: Connection = Depends(get_conn)):
    """How a will-call still out near closing gets the passenger home, on the record: the person on
    call for it, how they are reached and until when - or the other provider that has taken it,
    which makes the return theirs. Acknowledging is not coverage; this is."""
    acct = user["accountid"]
    leg = row(conn, "SELECT recordid, tripid, pickupat, outcomestate, brokerstate FROM triplegs "
                    "WHERE recordid = :l AND accountid = :a", l=legid, a=acct)
    if not leg:
        raise HTTPException(404, "No such leg")
    if leg["pickupat"] is not None or leg["outcomestate"] or leg["brokerstate"]:
        raise HTTPException(409, "This return is no longer waiting for its call.")
    clean = lambda v: (v or "").strip().upper()[:160] or None                  # noqa: E731
    if body.kind == "oncall":
        people = [(clean(p.person), clean(p.contact), p.until) for p in body.people]
        if not people or any(not p for p, _, _ in people):
            raise HTTPException(400, "Say who is covering it")
        if any(not c or not u for _, c, u in people):
            raise HTTPException(400, "Say how each person on call is reached, and until when.")
    elif body.kind == "other":
        person, contact = clean(body.person), clean(body.contact)
        if not person:
            raise HTTPException(400, "Say who is covering it")
        if not contact:
            raise HTTPException(400, "Give the other provider's confirmation.")
        people = [(person, contact, None)]
    else:
        raise HTTPException(400, "Say who is covering it")
    # One recording, one row per person: the rows written together are the coverage.
    now = utcnow()
    for p, c, u in people:
        run(conn, """
            INSERT INTO returncoverage (recordid, accountid, legid, kind, person, contact, until, recordedon, recordedby)
            VALUES (:id, :a, :l, :k, :p, :c, :u, :now, :by)
        """, id=newid(), a=acct, l=legid, k=body.kind, p=p, c=c, u=u, now=now, by=user["recordid"])
    if body.kind == "other":
        run(conn, "UPDATE triplegs SET responsibility = 'other', responsibilitynote = :n WHERE recordid = :l",
            n=f"{person} - {contact}"[:255], l=legid)
    elif row(conn, "SELECT 1 AS x FROM triplegs WHERE recordid = :l AND responsibility = 'unconfirmed'", l=legid):
        run(conn, "UPDATE triplegs SET responsibility = 'provider' WHERE recordid = :l", l=legid)
    log(conn, user, "return-coverage", "trip", leg["tripid"],
        {"legid": legid, "kind": body.kind,
         "people": [{"person": p, "contact": c, "until": str(u) if u else None} for p, c, u in people]},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/legs/{legid}/afterhours/reviewed")
def after_hours_reviewed(legid: str, request: Request, user: dict = Depends(editor),
                         conn: Connection = Depends(get_conn)):
    """The office has looked at a will-call the on-call driver took after closing: who took it,
    when, and what the app recorded. Until this, the trip is not billed."""
    acct = user["accountid"]
    leg = row(conn, "SELECT tripid, selfassignedon, afterhoursreviewedon FROM triplegs "
                    "WHERE recordid = :l AND accountid = :a", l=legid, a=acct)
    if not leg or not leg["selfassignedon"]:
        raise HTTPException(404, "No after-hours trip to review on that leg")
    if leg["afterhoursreviewedon"]:
        raise HTTPException(409, "This has already been reviewed.")
    run(conn, "UPDATE triplegs SET afterhoursreviewedon = :now, afterhoursreviewedby = :by "
              "WHERE recordid = :l AND accountid = :a", now=utcnow(), by=user["recordid"], l=legid, a=acct)
    log(conn, user, "afterhours-reviewed", "trip", leg["tripid"], {"legid": legid}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


# Why a trip is not going to happen. Chosen, not typed: a passenger who cancelled an hour before
# is a different event from a facility that cancelled last week, some contracts pay for one and
# not the other, and a free-text box cannot be reported on or sent to a broker.
CANCEL_REASONS = {
    "passenger": "The passenger canceled",
    "facility": "The facility canceled",
    "broker": "The broker canceled it",
    "nolongerneeded": "No longer needed",
    "duplicate": "Booked twice",
    "cannotcover": "We cannot cover it",
    "other": "Something else",
}


class CancelIn(BaseModel):
    reason: str
    note: str | None = None


@router.post("/trips/{tripid}/cancel")
def cancel_trip(tripid: str, body: CancelIn, request: Request, user: dict = Depends(editor),
                conn: Connection = Depends(get_conn)):
    """Call a trip off. Marked, never deleted.

    A deleted trip loses the fact that it was ever booked, and that is exactly what a broker asks
    about when it turns up on their reconciliation. A leg already driven is left alone: what
    happened, happened, and a cancellation cannot reach backwards and unhappen it."""
    acct = user["accountid"]
    held = row(conn, "SELECT recordid, cancelledon FROM trips WHERE recordid = :t "
                     "AND accountid = :a AND deleted IS NULL", t=tripid, a=acct)
    if not held:
        raise HTTPException(404, "No such trip")
    if held["cancelledon"]:
        raise HTTPException(409, "That trip is already canceled")
    if body.reason not in CANCEL_REASONS:
        raise HTTPException(400, "Say why it is being canceled")
    now = utcnow()
    run(conn, """
        UPDATE trips SET cancelreason = :r, cancelnote = :n, cancelledon = :now, cancelledby = :by,
                         updated = :now
        WHERE recordid = :t AND accountid = :a
    """, r=body.reason, n=(body.note or "").strip()[:400] or None, now=now,
        by=user["recordid"], t=tripid, a=acct)
    # Only the legs that have not been driven. An outbound completed this morning stays completed
    # when the return is called off this afternoon.
    # A disputed leg is settled by the cancellation, and says so on the dispute.
    for d in rows(conn, "SELECT recordid FROM triplegs WHERE tripid = :t AND accountid = :a "
                        "AND outcomestate = 'disputed'", t=tripid, a=acct):
        _settle_dispute(conn, acct, d["recordid"], "cancelled",
                        " - ".join(x for x in (CANCEL_REASONS.get(body.reason), (body.note or "").strip()) if x),
                        user["recordid"], now)
    # Each driver still on a leg that is now not going ahead is told.
    for g in rows(conn, """
        SELECT l.recordid, l.driverid, l.pickupat, t.externalid FROM triplegs l JOIN trips t ON t.recordid = l.tripid
        WHERE l.tripid = :t AND l.accountid = :a AND l.driverid IS NOT NULL AND l.executionstate <> 'completed'
          AND (l.outcomestate IS NULL OR l.outcomestate = 'disputed')
    """, t=tripid, a=acct):
        sms.tell(conn, acct, g["driverid"], "canceled",
                 f"Trip {g['externalid']}, pickup {sms.when(g['pickupat'])}, has been canceled. Open the app.",
                 tripid, g["recordid"])
    run(conn, """
        UPDATE triplegs SET outcomestate = 'cancelled'
        WHERE tripid = :t AND accountid = :a AND executionstate <> 'completed'
          AND (outcomestate IS NULL OR outcomestate = 'disputed')
    """, t=tripid, a=acct)
    # Nothing is driven, so nothing is owed: a cancelled trip must not sit in the billing queue
    # waiting for somebody to notice. Held rather than billed - whether a late cancellation is
    # chargeable is the fee schedule's question, asked by a person.
    run(conn, "UPDATE trips SET billingstatus = 'held' WHERE recordid = :t AND accountid = :a "
              "AND billingstatus = 'unbilled'", t=tripid, a=acct)
    log(conn, user, "trip-cancelled", "trip", tripid,
        {"reason": body.reason, "note": body.note}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/legs/{legid}/state")
def set_leg_state(legid: str, body: LegStateIn, request: Request, user: dict = Depends(editor),
                  conn: Connection = Depends(get_conn)):
    """Where this leg has got to, said by the office.

    The driver's app will say this for itself in phase two. Until then a dispatcher does it from
    what the driver tells them on the telephone, which is how it is done today on paper."""
    acct = user["accountid"]
    leg = row(conn, """
        SELECT l.recordid, l.tripid FROM triplegs l
        JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        WHERE l.recordid = :id AND l.accountid = :a
    """, id=legid, a=acct)
    if not leg:
        raise HTTPException(404, "No such leg")
    if body.executionstate and body.executionstate not in EXECUTION:
        raise HTTPException(400, "Unknown state")
    if body.outcomestate and body.outcomestate not in OUTCOMES:
        raise HTTPException(400, "Unknown outcome")
    if body.executionstate:
        run(conn, "UPDATE triplegs SET executionstate = :s WHERE recordid = :l AND accountid = :a",
            s=body.executionstate, l=legid, a=acct)
        # Recorded the same way the driver's own app records it, and saying who said so - an
        # arrival the office typed in is evidence of a different kind from one a driver reported
        # from the kerb, and the record has to be able to tell them apart.
        run(conn, """
            INSERT INTO tripevents (recordid, accountid, legid, state, happenedon, recordedon,
                                    byuserid)
            VALUES (:id, :a, :l, :s, :now, :now, :by)
        """, id=newid(), a=acct, l=legid, s=body.executionstate, now=utcnow(),
            by=user["recordid"])
    if body.outcomestate is not None:
        run(conn, "UPDATE triplegs SET outcomestate = :s WHERE recordid = :l AND accountid = :a",
            s=body.outcomestate or None, l=legid, a=acct)
    # A trip whose every leg has been driven is waiting to be read before anybody bills it.
    done = row(conn, """
        SELECT COUNT(*) AS legs, SUM(executionstate = 'completed') AS finished
        FROM triplegs WHERE tripid = :t AND accountid = :a
    """, t=leg["tripid"], a=acct) or {}
    if int(done.get("legs") or 0) and int(done.get("finished") or 0) == int(done["legs"]):
        run(conn, "UPDATE trips SET verifystate = 'awaitingreview', updated = :now "
                  "WHERE recordid = :t AND verifystate = 'notready'", now=utcnow(), t=leg["tripid"])
    log(conn, user, "trip-leg-state", "trip", leg["tripid"],
        {"legid": legid, "executionstate": body.executionstate,
         "outcomestate": body.outcomestate}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


EXECUTION = ("scheduled", "enroute", "arrived", "onboard", "completed")
OUTCOMES = ("", "cancelled", "noshow", "aborted", "disputed")

# What a trip that did not happen turns out to have been. A missed pickup is a question, not an
# answer: until somebody rings the driver, "Missed" means only that nobody pressed anything.
#
# The four are kept apart because they are paid differently and reported differently. A passenger
# who did not come out is a no-show, which most broker contracts pay a fee for and which has a
# procedure attached; a trip nobody drove is the company's own failure and is not billable at all;
# and a trip that WAS driven by somebody who forgot the app is not an outcome - it is a record
# that needs filling in.
WHAT_HAPPENED = {
    "driven": "It Was Driven",
    "noshow": "Passenger No-Show",
    "aborted": "Not Done By Us",
    "disputed": "In Dispute",
}


class OutcomeIn(BaseModel):
    outcome: str
    note: str | None = None
    pickedupat: datetime | None = None
    droppedoffat: datetime | None = None
    miles: float | None = None        # driven: how far it ran, as the office knows it


@router.post("/legs/{legid}/outcome")
def record_what_happened(legid: str, body: OutcomeIn, request: Request,
                         user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Close out a leg that did not go as planned.

    Somebody has rung the driver and now knows. This writes down which of the four it was, so the
    trip stops sitting on the board as an open question and so billing is told the truth: a
    no-show may be chargeable, a trip nobody drove is not."""
    acct = user["accountid"]
    leg = row(conn, """
        SELECT l.recordid, l.tripid, l.pickupat, l.outcomestate FROM triplegs l
        JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        WHERE l.recordid = :id AND l.accountid = :a
    """, id=legid, a=acct)
    if not leg:
        raise HTTPException(404, "No such leg")
    if body.outcome not in WHAT_HAPPENED:
        raise HTTPException(400, "Say what happened")
    note = (body.note or "").strip()
    settling = leg["outcomestate"] == "disputed"
    if body.outcome == "disputed":
        if settling:
            raise HTTPException(409, "This leg is already in dispute. Settle it.")
        if not note:
            raise HTTPException(400, "Say what is in dispute")
    if settling and not note:
        raise HTTPException(400, "Say how the dispute was settled")
    now = utcnow()
    if body.outcome == "disputed":
        run(conn, """
            INSERT INTO tripdisputes (recordid, accountid, tripid, legid, raisedon, raisedby, reason)
            VALUES (:id, :a, :t, :l, :now, :by, :r)
        """, id=newid(), a=acct, t=leg["tripid"], l=legid, now=now, by=user["recordid"], r=note[:2000])
    elif settling:
        _settle_dispute(conn, acct, legid, body.outcome, note, user["recordid"], now)

    if body.outcome == "driven":
        # Not an outcome. The trip happened; the record of it is what is missing, and it is being
        # entered by the office rather than by the driver - which the event says, so an auditor
        # can tell a recorded arrival from a reported one.
        if not body.droppedoffat:
            raise HTTPException(400, "Say when the passenger was dropped off")
        # What the office types here is a WALL CLOCK time, the same kind the pickup is stored
        # as - "2:40" means twenty to three in Florida. So it is checked against the company's
        # clock, never the server's, or an afternoon drop-off entered at teatime is refused as
        # being in the future.
        zone = user.get("timezone") or _account_zone(conn, acct)
        began = body.pickedupat or leg["pickupat"]
        if began and body.droppedoffat < began:
            raise HTTPException(400, "The drop-off cannot be before the pickup")
        if body.droppedoffat > localnow(zone):
            raise HTTPException(400, "That drop-off is in the future")
        run(conn, """
            UPDATE triplegs SET executionstate = 'completed', outcomestate = NULL,
                   pickupat = COALESCE(:picked, pickupat), dropoffat = :dropped
            WHERE recordid = :l AND accountid = :a
        """, picked=body.pickedupat, dropped=body.droppedoffat, l=legid, a=acct)
        run(conn, """
            INSERT INTO tripevents (recordid, accountid, legid, state, happenedon, recordedon,
                                    byuserid)
            VALUES (:id, :a, :l, 'completed', :on, :now, :by)
        # tripevents.happenedon is an INSTANT, in UTC, because it sits beside moments a phone
        # reported from wherever it was. The wall clock the office typed has to become one.
        """, id=newid(), a=acct, l=legid, on=_as_instant(body.droppedoffat, zone), now=now,
             by=user["recordid"])
        if body.miles is not None:
            dispatch.plausible_miles(body.miles)
            run(conn, """UPDATE triplegs SET officemiles = :m, officemilesreason = 'ENTERED WHEN THE OFFICE CLOSED OUT THE LEG',
                         officemilesby = :by, officemileson = :now WHERE recordid = :l""", m=body.miles, by=user["recordid"], now=now, l=legid)
        _settle_verify_from_office(conn, acct, leg["tripid"])
    else:
        run(conn, "UPDATE triplegs SET outcomestate = :o WHERE recordid = :l AND accountid = :a",
            o=body.outcome, l=legid, a=acct)
        # A trip nobody drove must not wait in the billing queue for somebody to notice. A
        # no-show might be chargeable - the fee schedule prices one - so it goes to be read
        # rather than being decided here.
        run(conn, """
            UPDATE trips SET verifystate = 'awaitingreview', updated = :now
            WHERE recordid = :t AND accountid = :a AND verifystate = 'notready'
        """, now=now, t=leg["tripid"], a=acct)
        if body.outcome == "aborted":
            run(conn, "UPDATE trips SET billingstatus = 'held' WHERE recordid = :t "
                      "AND accountid = :a AND billingstatus = 'unbilled'",
                t=leg["tripid"], a=acct)
    log(conn, user, "trip-outcome", "trip", leg["tripid"],
        {"legid": legid, "outcome": body.outcome, "note": body.note}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


def _settle_verify_from_office(conn: Connection, accountid: str, tripid: str) -> None:
    done = row(conn, """
        SELECT COUNT(*) AS legs, SUM(executionstate = 'completed') AS finished
        FROM triplegs WHERE tripid = :t AND accountid = :a
    """, t=tripid, a=accountid) or {}
    if int(done.get("legs") or 0) and int(done.get("finished") or 0) == int(done["legs"]):
        run(conn, "UPDATE trips SET verifystate = 'awaitingreview', updated = :now "
                  "WHERE recordid = :t AND verifystate = 'notready'", now=utcnow(), t=tripid)


def _settle_dispatch_state(conn: Connection, accountid: str, tripid: str) -> None:
    """A trip is covered when every one of its legs has a driver. Worked out from the legs rather
    than set by whoever happened to touch it last - a reservation with a return leg nobody has
    taken is not an assigned trip, however many times the outbound was reassigned."""
    held = row(conn, """
        SELECT COUNT(*) AS legs, SUM(driverid IS NOT NULL) AS covered
        FROM triplegs WHERE tripid = :t AND accountid = :a
    """, t=tripid, a=accountid) or {}
    legs, covered = int(held.get("legs") or 0), int(held.get("covered") or 0)
    state = "assigned" if legs and covered == legs else "unassigned"
    run(conn, "UPDATE trips SET dispatchstate = :s, updated = :now WHERE recordid = :t AND accountid = :a",
        s=state, now=utcnow(), t=tripid, a=accountid)


def _shadow_check(conn: Connection, accountid: str, driverid: str | None, vehicleid: str | None,
                  legid: str, userid: str) -> None:
    """The trip eligibility check on every assignment. An assignment that fails anything
    enforceable - a rule a reviewer approved, or a plain fact such as no lift for a wheelchair
    trip - is refused, with the reason. A draft rule is never enforced."""
    if not driverid:
        return
    # Always enforced: a company cannot switch off a requirement the law or its contracts impose.
    enforce = True
    try:
        got = tripcheck.check(conn, accountid, driverid, vehicleid, legid=legid, userid=userid,
                              shadow=not enforce)
    except Exception:                       # noqa: BLE001 - see above
        if enforce:
            raise
        return
    if enforce and got["enforceable"]:
        first = got["enforceable"][0]
        # The refusal rolls the assignment back, and would take the check with it. The check is
        # written again in a transaction of its own, marked refused, so the file keeps the answer
        # that stopped the assignment.
        try:
            from app.db import engine
            with engine.begin() as kept:
                again = tripcheck.check(kept, accountid, driverid, vehicleid, legid=legid,
                                        userid=userid)
                run(kept, "UPDATE tripeligibility SET refused = 1 WHERE recordid = :id",
                    id=again["evaluationid"])
        except Exception:                   # noqa: BLE001 - the refusal stands regardless
            pass
        # A vehicle's own problem is said; the driver's is not - only that they are not eligible.
        if first.get("vehicle") or first.get("code") in dispatch.SAID_IN_FULL:
            raise HTTPException(409, f'This driver cannot take this trip: '
                                     f'{first.get("name") + " - " if first.get("name") else ""}'
                                     f'{first.get("reason")}')
        raise HTTPException(409, f"This driver is {dispatch.NOT_ELIGIBLE.lower()}.")


class EligibilityIn(BaseModel):
    driverid: str
    vehicleid: str | None = None
    legid: str | None = None
    program: str | None = None
    at: datetime | None = None


@router.post("/dispatch/eligibility-check")
def eligibility_check(body: EligibilityIn, user: dict = Depends(current_user),
                      conn: Connection = Depends(get_conn)):
    """May this driver, in this vehicle, take this trip - and why not. Recorded either way."""
    got = tripcheck.check(conn, user["accountid"], body.driverid, body.vehicleid, legid=body.legid,
                          program=body.program, at=body.at, userid=user["recordid"])
    saved(conn)
    return got


@router.get("/drivers/{driverid}/eligibility-checks")
def eligibility_history(driverid: str, user: dict = Depends(current_user),
                        conn: Connection = Depends(get_conn)):
    """Every trip check made on this driver, newest first."""
    return {"checks": [{**c, "blockers": json.loads(c["blockers"] or "[]"),
                        "warnings": json.loads(c["warnings"] or "[]")} for c in rows(conn, """
        SELECT recordid, legid, vehicleid, program, evaluatedfor, evaluatedon, decision, blockers,
               warnings, shadow FROM tripeligibility
        WHERE accountid = :a AND driverid = :d ORDER BY evaluatedon DESC LIMIT 100
    """, a=user["accountid"], d=driverid)]}
