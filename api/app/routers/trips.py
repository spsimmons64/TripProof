###################################################################################################
# The trip ledger - imports, the trip list (the pre-billing scrub), trip detail, re-evaluation.
#
# PHI is never in a list response. Trip detail returns operational facts only; member identity and
# addresses come from a separate endpoint that logs the access (minimum necessary).
###################################################################################################
import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import dispatch, importer, phi
from app import wheremap
from app.activity import log
from app.db import get_conn, newid, row, rows, run, saved, utcnow
from app.evaluator import evaluate
from app.security import client_ip, current_user, editor

router = APIRouter(prefix="/api", tags=["trips"])

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

@router.get("/trips")
def list_trips(status: str = "all", billing: str | None = None, datefrom: str | None = None, dateto: str | None = None,
               q: str | None = None, driverid: str | None = None, vehicleid: str | None = None,
               page: int = 1, pagesize: int = 100,
               user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    pagesize = max(1, min(pagesize, 500))
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
        ORDER BY t.tripdate DESC, t.externalid
        LIMIT :lim OFFSET :off
    """, lim=pagesize, off=(max(page, 1) - 1) * pagesize, **params)
    return {"total": total["n"], "amount": total["amount"], "page": page, "pagesize": pagesize, "items": items}


class Leg(BaseModel):
    pickupat: datetime
    dropoffat: datetime | None = None
    pickupplace: str
    dropoffplace: str
    driverid: str | None = None
    vehicleid: str | None = None


class Booking(BaseModel):
    passenger: str
    passengerphone: str | None = None
    tripdate: date
    servicelevel: str = "ambulatory"
    payer: str = "private"
    brokerid: str | None = None
    note: str | None = None
    legs: list[Leg]


@router.get("/trips/suggest")
def who_should_take_it(when: datetime, minutes: int = 60, service: str = "ambulatory",
                       seats: int = 1, pickup: str | None = None,
                       user: dict = Depends(current_user),
                       conn: Connection = Depends(get_conn)):
    """Which driver and which vehicle suit a job, and the reasons for the order.

    `pickup` is "lat,lng" where the office has it. Without it the ranking still works - it
    just cannot sort by who is nearest, and says so against each driver."""
    at = None
    if pickup:
        try:
            lat, lng = (float(x) for x in pickup.split(",", 1))
            at = (lat, lng)
        except ValueError:
            raise HTTPException(400, "pickup must be lat,lng") from None
    return dispatch.best(conn, user["accountid"], when=when, minutes=minutes,
                         service=service, seats=seats, pickup=at)


@router.post("/trips")
def book_a_trip(body: Booking, request: Request, user: dict = Depends(editor),
                conn: Connection = Depends(get_conn)):
    """Book a trip by hand - the private pay and telephone case.

    The imported trips arrive priced; this one does not. `billedamount` is zero until a fee
    schedule exists to work it out, and saying zero is honest where inventing a number is
    not."""
    acct = user["accountid"]
    if not body.legs:
        raise HTTPException(400, "A trip needs at least one leg")
    if body.servicelevel not in dispatch.SERVICE:
        raise HTTPException(400, f"Unknown service level {body.servicelevel}")
    tripid = newid()
    # Its own reference until a broker gives it one. Visibly local, so nobody mistakes it for
    # a broker's number when the two sit in one list.
    external = f"TP-{body.tripdate:%Y%m%d}-{tripid[:6].upper()}"
    run(conn, """
        INSERT INTO trips (recordid, accountid, externalid, tripdate, servicelevel,
                           billedamount, billingstatus, brokerid, passenger, passengerphone,
                           payer, note, bookedby, added)
        VALUES (:id, :a, :x, :on, :svc, 0, 'unbilled', :b, :p, :ph, :pay, :n, :by, :now)
    """, id=tripid, a=acct, x=external, on=body.tripdate, svc=body.servicelevel,
        b=body.brokerid, p=body.passenger.strip()[:160],
        ph=(body.passengerphone or "").strip()[:32] or None, pay=body.payer[:16],
        n=(body.note or "").strip()[:512] or None, by=user["recordid"], now=utcnow())

    for n, leg in enumerate(body.legs, start=1):
        # Placed once, here, so the dispatch screen can sort by distance later without
        # geocoding the same address on every page load.
        here = wheremap.place(leg.pickupplace)
        there = wheremap.place(leg.dropoffplace)
        run(conn, """
            INSERT INTO triplegs (recordid, accountid, tripid, legnumber, driverid, vehicleid,
                                  vehicleexternal, pickupat, dropoffat, pickupplace, pickuplat,
                                  pickuplng, dropoffplace, dropofflat, dropofflng,
                                  servicelevel, loaded, signature, gps, added)
            VALUES (:id, :a, :t, :n, :d, :v, :vx, :pa, :da, :pp, :plat, :plng, :dp, :dlat,
                    :dlng, :svc, :loaded, 0, 0, :now)
        """, id=newid(), a=acct, t=tripid, n=n, d=leg.driverid, v=leg.vehicleid,
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

    log(conn, user, "trip-booked", "trip", tripid,
        {"passenger": body.passenger, "legs": len(body.legs)}, ip=client_ip(request))
    saved(conn)
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
        SELECT l.recordid, l.legnumber, l.pickupat, l.dropoffat, l.signature, l.gps, l.driverid, l.vehicleid,
               l.driverexternal, l.vehicleexternal, CONCAT(d.firstname, ' ', d.lastname) AS drivername,
               v.externalid AS unit, v.modelyear
        FROM triplegs l LEFT JOIN drivers d ON d.recordid = l.driverid LEFT JOIN vehicles v ON v.recordid = l.vehicleid
        WHERE l.tripid = :id ORDER BY l.legnumber
    """, id=tripid)
    t["checks"] = rows(conn, """
        SELECT c.legid, c.subject, c.outcome, c.reasoncode, c.reason, c.credentialid, c.windowstart, c.windowend,
               q.code, q.description, r.family, r.version, r.verified, cr.number, cr.issuedon, cr.expireson, cr.documentid
        FROM legchecks c
        JOIN requirements q ON q.recordid = c.requirementid
        JOIN rulesets r ON r.recordid = q.rulesetid
        LEFT JOIN credentials cr ON cr.recordid = c.credentialid
        WHERE c.tripid = :id AND c.runid = :run
        ORDER BY c.outcome = 'pass', r.family, q.code
    """, id=tripid, run=t["lastrunid"])
    t["run"] = row(conn, "SELECT recordid, reason, engineversion, finished FROM evaluationruns WHERE recordid = :r",
                   r=t["lastrunid"]) if t["lastrunid"] else None
    return t


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
    r = run(conn, "UPDATE trips SET billingstatus = :s, updated = :now WHERE recordid = :id AND accountid = :a",
            s=body.billingstatus, now=utcnow(), id=tripid, a=user["accountid"])
    if not r.rowcount:
        raise HTTPException(404, "Trip not found")
    log(conn, user, "update", "trip", tripid, {"billingstatus": body.billingstatus})
    return {"ok": True}


@router.post("/evaluate")
def evaluate_all(user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    result = evaluate(conn, user["accountid"], None, user["recordid"], "manual")
    log(conn, user, "evaluate", "evaluationrun", result["runid"], result)
    return result
