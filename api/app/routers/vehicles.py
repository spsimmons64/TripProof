"""Vehicles, The fleet's own compliance file - moved out of routers/vault.py, which grew too large to work in safely.

Shared helpers still live in vault and are imported from there."""
import hashlib
import io
import json
import logging
import re
import secrets
import zipfile
from datetime import date, datetime, time, timedelta
from html import escape

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import (accidents, annualreview, applicationview, backgroundchecks, billing,
                 invitations,
                 certn, documents, drivers,
                 eligibility, emails, exposure,
                 employers, events, gfeview, hos, i9, misreport, pdfform, randompool,
                 roadtest, roadtestview,
                 mvr as mvrs,
                 facts as factset, formats, images, mailer, phi, qualification, rules,
                 screening, screeningaccount, signatures, storage, tripcheck,
                 rates as rateset, vehicleclass, wheremap)
from app import dispatch, gateways, payerlines
from app.routers import signing, uploading
from app.activity import log
from app.config import settings
from app.db import get_conn, localnow, newid, row, rows, run, saved, utcnow
from app.evaluator import evaluate
from app.profiles import PROFILE_FIELDS, clean_profile
from app.routers import admin
from app.security import account_admin, client_ip, current_user, editor
from app.validity import credential_window
from app.routers.vault import (  # noqa: F401 - shared helpers
    ADVERSE_STATUS,
    _credentials,
    _exposure_by,
    _latest_by_type,
    _mark_replaced,
    _reevaluate_subject,
    _status_today,
)

router = APIRouter(prefix="/api", tags=["vault"])


# ------------------------------------------------------------------------------------------------
# Vehicles
# ------------------------------------------------------------------------------------------------

class VehicleIn(BaseModel):
    externalid: str | None = None
    vin: str | None = None
    plate: str | None = None
    make: str | None = None
    model: str | None = None
    modelyear: int | None = None
    odometer: int | None = None
    odometerasof: date | None = None
    gvwr: int | None = None
    gcwr: int | None = None             # combination rating; 390.5 reads the greater of the two
    seats: int | None = None            # designed occupancy including the driver
    forcompensation: bool = False       # passengers carried for hire - the 390.5(2) prong
    lift: bool | None = None


# ------------------------------------------------------------------------------------------------
# The fleet's own compliance file: what each vehicle owes, its inspection reports and its servicing
# ------------------------------------------------------------------------------------------------

DVIR_KINDS = {"pretrip": "Pre-trip", "posttrip": "Post-trip"}
SERVICE_KINDS = {"scheduled": "Scheduled maintenance", "repair": "Repair",
                 "inspection": "Inspection"}


def _vehicle(conn: Connection, acct: str, vehicleid: str) -> dict:
    got = row(conn, """
        SELECT recordid, externalid, vin, plate, make, model, modelyear, lift
        FROM vehicles WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=vehicleid, a=acct)
    if not got:
        raise HTTPException(404, "No such vehicle")
    return got


@router.get("/vehicles/requirements")
def fleet_requirements(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Every vehicle and what it still owes. The fleet equivalent of the driver roster."""
    acct = user["accountid"]
    today = localnow(user["timezone"]).date()
    out = []
    for v in rows(conn, """
        SELECT recordid, externalid, vin, make, model, modelyear FROM vehicles
        WHERE accountid = :a AND deleted IS NULL AND stub = 0 ORDER BY externalid, vin
    """, a=acct):
        items = rules.for_vehicle(conn, acct, v["recordid"],
                                  factset.assemble(conn, acct, vehicleid=v["recordid"])["facts"],
                                  today=today)
        live = [i for i in items if i["applies"] is True]
        out.append({**v,
                    "outstanding": [i["code"] for i in live
                                    if i["status"] in ADVERSE_STATUS or i["status"] == "pending"],
                    "stops": [i["code"] for i in live if i["gate"] == "hardstop"
                              and (i["status"] in ADVERSE_STATUS or i["status"] == "pending")],
                    "expiring": [i["code"] for i in live if i["status"] == "expiring"]})
    return {"vehicles": out}


@router.get("/vehicles/{vehicleid}/requirements")
def vehicle_requirements(vehicleid: str, user: dict = Depends(current_user),
                         conn: Connection = Depends(get_conn)):
    """What is asked of this vehicle, why, and where it stands on each of it."""
    acct = user["accountid"]
    _vehicle(conn, acct, vehicleid)
    gathered = factset.assemble(conn, acct, vehicleid=vehicleid)
    items = rules.for_vehicle(conn, acct, vehicleid, gathered["facts"],
                              today=localnow(user["timezone"]).date())
    counted: dict[str, int] = {}
    for i in items:
        counted[i["status"]] = counted.get(i["status"], 0) + 1
    return {"items": items, "counts": counted,
            "types": {r["code"]: r["recordid"] for r in rows(conn, """
                SELECT code, recordid FROM credentialtypes
                WHERE subject = 'vehicle' AND active = 1""")}}


@router.get("/vehicles/{vehicleid}/dvirs")
def vehicle_dvirs(vehicleid: str, user: dict = Depends(current_user),
                  conn: Connection = Depends(get_conn)):
    """The inspection reports on this vehicle, newest first, and what is still open."""
    acct = user["accountid"]
    _vehicle(conn, acct, vehicleid)
    held = rows(conn, """
        SELECT v.recordid, v.reportedon, v.kind, v.defects, v.defectnote, v.correctedon,
               v.correctedby, v.certifiedon, v.documentid, v.note,
               CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, '')) AS drivername,
               v.driverid
        FROM vehicledvirs v LEFT JOIN drivers d ON d.recordid = v.driverid
        WHERE v.accountid = :a AND v.vehicleid = :v AND v.deleted IS NULL
        ORDER BY v.reportedon DESC, v.added DESC
    """, a=acct, v=vehicleid)
    return {
        "reports": held,
        "kinds": DVIR_KINDS,
        # What stops the vehicle: a defect reported and not put right. 49 CFR 396.11(a)(3).
        "open": [r for r in held if r["defects"] and not r["correctedon"]],
        "drivers": rows(conn, """
            SELECT recordid, firstname, lastname FROM drivers
            WHERE accountid = :a AND deleted IS NULL AND stub = 0 AND terminatedon IS NULL
            ORDER BY lastname, firstname
        """, a=acct),
    }


@router.post("/vehicles/{vehicleid}/dvirs")
async def record_dvir(
    vehicleid: str,
    request: Request,
    reportedon: date = Form(...),
    kind: str = Form(...),
    defects: bool = Form(False),
    defectnote: str | None = Form(None),
    driverid: str | None = Form(None),
    note: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    """File one inspection report."""
    acct = user["accountid"]
    _vehicle(conn, acct, vehicleid)
    if kind not in DVIR_KINDS:
        raise HTTPException(400, "Say whether it was a pre-trip or a post-trip inspection")
    if reportedon > localnow(user["timezone"]).date():
        raise HTTPException(400, "That date has not happened yet")
    if defects and not (defectnote or "").strip():
        raise HTTPException(400, "Say what the defect was")
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    run(conn, """
        INSERT INTO vehicledvirs (recordid, accountid, vehicleid, driverid, reportedon, kind,
                                  defects, defectnote, documentid, note, addedby)
        VALUES (:id, :a, :v, :d, :on, :k, :hasdefect, :dn, :doc, :n, :by)
    """, id=newid(), a=acct, v=vehicleid, d=(driverid or None), on=reportedon, k=kind,
        hasdefect=int(defects), dn=(defectnote or "").strip()[:512] or None, doc=documentid,
        n=(note or "").strip()[:512] or None, by=user["recordid"])
    log(conn, user, "dvir", "vehicle", vehicleid,
        {"reportedon": str(reportedon), "kind": kind, "defects": defects},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class CorrectionIn(BaseModel):
    correctedon: date
    correctedby: str | None = None
    note: str | None = None


@router.put("/vehicles/{vehicleid}/dvirs/{recordid}/corrected")
def correct_dvir(vehicleid: str, recordid: str, body: CorrectionIn, request: Request,
                 user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Certify that a reported defect has been put right, which is what lets the vehicle out."""
    acct = user["accountid"]
    _vehicle(conn, acct, vehicleid)
    n = run(conn, """
        UPDATE vehicledvirs SET correctedon = :on, correctedby = :by, certifiedon = :now,
               note = COALESCE(:n, note)
        WHERE recordid = :id AND accountid = :a AND vehicleid = :v AND deleted IS NULL
          AND defects = 1 AND correctedon IS NULL
    """, on=body.correctedon, by=(body.correctedby or "").strip()[:160] or None,
        now=localnow(user["timezone"]).date(), n=(body.note or "").strip()[:512] or None,
        id=recordid, a=acct, v=vehicleid).rowcount
    if not n:
        raise HTTPException(404, "There is no outstanding defect on that report")
    log(conn, user, "dvir-corrected", "vehicle", vehicleid, {"recordid": recordid},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.delete("/vehicles/{vehicleid}/dvirs/{recordid}")
def remove_dvir(vehicleid: str, recordid: str, request: Request, user: dict = Depends(editor),
                conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    n = run(conn, """
        UPDATE vehicledvirs SET deleted = :now
        WHERE recordid = :id AND accountid = :a AND vehicleid = :v AND deleted IS NULL
    """, now=utcnow(), id=recordid, a=acct, v=vehicleid).rowcount
    if not n:
        raise HTTPException(404, "No such report")
    log(conn, user, "dvir-withdrawn", "vehicle", vehicleid, {"recordid": recordid},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.get("/vehicles/{vehicleid}/maintenance")
def vehicle_maintenance(vehicleid: str, user: dict = Depends(current_user),
                        conn: Connection = Depends(get_conn)):
    """What has been done to this vehicle, newest first."""
    acct = user["accountid"]
    _vehicle(conn, acct, vehicleid)
    return {
        "kinds": SERVICE_KINDS,
        "records": rows(conn, """
            SELECT m.recordid, m.performedon, m.kind, m.odometer, m.summary, m.vendor,
                   m.documentid, m.note, u.name AS addedbyname
            FROM vehiclemaintenance m LEFT JOIN users u ON u.recordid = m.addedby
            WHERE m.accountid = :a AND m.vehicleid = :v AND m.deleted IS NULL
            ORDER BY m.performedon DESC, m.added DESC
        """, a=acct, v=vehicleid),
    }


@router.post("/vehicles/{vehicleid}/maintenance")
async def record_maintenance(
    vehicleid: str,
    request: Request,
    performedon: date = Form(...),
    kind: str = Form(...),
    summary: str = Form(...),
    odometer: int | None = Form(None),
    vendor: str | None = Form(None),
    note: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    """Record one piece of work, which is what 49 CFR 396.3(b) asks to be kept."""
    acct = user["accountid"]
    _vehicle(conn, acct, vehicleid)
    if kind not in SERVICE_KINDS:
        raise HTTPException(400, "Say what kind of work it was")
    if not summary.strip():
        raise HTTPException(400, "Say what was done")
    if performedon > localnow(user["timezone"]).date():
        raise HTTPException(400, "That date has not happened yet")
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    run(conn, """
        INSERT INTO vehiclemaintenance (recordid, accountid, vehicleid, performedon, kind, odometer,
                                        summary, vendor, documentid, note, addedby)
        VALUES (:id, :a, :v, :on, :k, :odo, :s, :vend, :doc, :n, :by)
    """, id=newid(), a=acct, v=vehicleid, on=performedon, k=kind, odo=odometer,
        s=summary.strip()[:255], vend=(vendor or "").strip()[:160] or None, doc=documentid,
        n=(note or "").strip()[:512] or None, by=user["recordid"])
    # The odometer on the vehicle moves with the newest reading, so the fleet record does not go
    # stale behind its own maintenance log.
    if odometer:
        run(conn, """
            UPDATE vehicles SET odometer = :odo, odometerasof = :on, updated = :now
            WHERE recordid = :v AND accountid = :a
              AND (odometerasof IS NULL OR odometerasof <= :on)
        """, odo=odometer, on=performedon, now=utcnow(), v=vehicleid, a=acct)
    log(conn, user, "maintenance", "vehicle", vehicleid,
        {"performedon": str(performedon), "kind": kind}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.delete("/vehicles/{vehicleid}/maintenance/{recordid}")
def remove_maintenance(vehicleid: str, recordid: str, request: Request,
                       user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    n = run(conn, """
        UPDATE vehiclemaintenance SET deleted = :now
        WHERE recordid = :id AND accountid = :a AND vehicleid = :v AND deleted IS NULL
    """, now=utcnow(), id=recordid, a=acct, v=vehicleid).rowcount
    if not n:
        raise HTTPException(404, "No such record")
    log(conn, user, "maintenance-withdrawn", "vehicle", vehicleid, {"recordid": recordid},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.get("/vehicles")
def list_vehicles(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    vehicles = rows(conn, """
        SELECT recordid, externalid, vin, plate, make, model, modelyear, seats, lift, gvwr, gcwr,
               forcompensation, odometer, stub
        FROM vehicles WHERE accountid = :a AND deleted IS NULL ORDER BY externalid, vin
    """, a=acct)
    creds = _credentials(conn, acct, "vehicle")
    exposure = _exposure_by(conn, acct, "vehicle")
    today = localnow(user["timezone"])
    by_vehicle: dict[str, list] = {}
    for c in creds:
        by_vehicle.setdefault(c["subjectid"], []).append(c)
    for v in vehicles:
        v["license"] = vehicleclass.license_for(v)
        latest = _latest_by_type(by_vehicle.get(v["recordid"], []), today)
        v["credentials"] = len(latest)
        v["expired"] = sum(1 for c in latest.values() if c["state"] in ("expired", "revoked"))
        v["expiring"] = sum(1 for c in latest.values() if c["state"] == "expiring")
        e = exposure.get(v["recordid"])
        v["risktrips"] = e["trips"] if e else 0
        v["riskamount"] = e["amount"] if e else 0
    return vehicles


@router.post("/vehicles")
def create_vehicle(body: VehicleIn, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    vid = newid()
    run(conn, """
        INSERT INTO vehicles (recordid, accountid, externalid, vin, plate, make, model, modelyear,
                              seats, lift, odometer, odometerasof, gvwr, gcwr, forcompensation)
        VALUES (:id, :a, :ext, :vin, :plate, :make, :model, :yr, :seats, :lift, :odo, :odoasof, :gvwr,
                :gcwr, :hire)
    """, id=vid, a=user["accountid"], ext=body.externalid or None, vin=(body.vin or "").upper() or None,
        plate=body.plate, make=body.make, model=body.model, yr=body.modelyear, seats=body.seats,
        lift=int(bool(body.lift)), odo=body.odometer, odoasof=body.odometerasof, gvwr=body.gvwr,
        gcwr=body.gcwr, hire=int(bool(body.forcompensation)))
    log(conn, user, "create", "vehicle", vid)
    return {"recordid": vid}


@router.get("/vehicles/{vehicleid}")
def get_vehicle(vehicleid: str, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    v = row(conn, "SELECT * FROM vehicles WHERE recordid = :id AND accountid = :a AND deleted IS NULL", id=vehicleid, a=acct)
    if v:
        v["license"] = vehicleclass.license_for(v)
        # What follows from the measurements, with the reason for each - never stored, always shown.
        v["facts"] = vehicleclass.facts(v)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    today = localnow(user["timezone"])
    v["credentials"] = _mark_replaced([_status_today(c, today) for c in _credentials(conn, acct, "vehicle", vehicleid)])
    v["exposure"] = _exposure_by(conn, acct, "vehicle").get(vehicleid, {"trips": 0, "amount": 0})
    return v


@router.put("/vehicles/{vehicleid}")
def update_vehicle(vehicleid: str, body: VehicleIn, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    r = run(conn, """
        UPDATE vehicles SET externalid = :ext, vin = :vin, plate = :plate, make = :make, model = :model,
               modelyear = :yr, seats = :seats, lift = :lift, odometer = :odo, odometerasof = :odoasof,
               gvwr = :gvwr, gcwr = :gcwr, forcompensation = :hire, stub = 0, updated = :now
        WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=vehicleid, a=user["accountid"], ext=body.externalid or None, vin=(body.vin or "").upper() or None,
        plate=body.plate, make=body.make, model=body.model, yr=body.modelyear, seats=body.seats,
        lift=int(bool(body.lift)), odo=body.odometer, odoasof=body.odometerasof, gvwr=body.gvwr,
        gcwr=body.gcwr, hire=int(bool(body.forcompensation)), now=utcnow())
    if not r.rowcount:
        raise HTTPException(404, "Vehicle not found")
    log(conn, user, "update", "vehicle", vehicleid, body.model_dump(mode="json"))
    # Model year and odometer feed the vehicle age and mileage rules.
    return {"ok": True, "evaluation": _reevaluate_subject(conn, user, "vehicle", vehicleid)}
