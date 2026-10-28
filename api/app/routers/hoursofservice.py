"""Hours of service - moved out of routers/vault.py, which grew too large to work in safely.

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
    _applicant,
    _reevaluate_subject,
)

router = APIRouter(prefix="/api", tags=["vault"])


# ------------------------------------------------------------------------------------------------
# Hours of service - F.A.C. 14-90.006
#
# A day of work, recorded. The limits and the rolling seven-day window live in app/hos.py so the
# requirement and this screen cannot come to different conclusions about the same driver.
# ------------------------------------------------------------------------------------------------

class DutyDayIn(BaseModel):
    dutydate: date
    dutystart: str | None = None
    dutyend: str | None = None
    drivingminutes: int = 0
    ondutyminutes: int = 0
    note: str | None = None


@router.get("/drivers/{driverid}/duty-days")
def driver_duty_days(driverid: str, user: dict = Depends(current_user),
                     conn: Connection = Depends(get_conn)):
    """The driver's work, newest first, with where they stand against the limits."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    days = hos.days_for(conn, acct, driverid)
    over = {}
    for b in hos.breaches(days):
        over.setdefault(str(b["dutydate"]), []).append(b["why"])
    return {"days": [{**d, "breaches": over.get(str(d["dutydate"]), [])}
                     for d in reversed(days)],
            "standing": hos.standing(conn, acct, driverid),
            "limits": {"driving": hos.DRIVING_LIMIT, "duty": hos.DUTY_LIMIT,
                       "week": hos.WEEK_LIMIT}}


@router.post("/drivers/{driverid}/duty-days")
def record_duty_day(driverid: str, body: DutyDayIn, request: Request,
                    user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Record, or correct, one day of work.

    One row per driver per day: a correction replaces the day rather than adding a second
    version of it, because two rows for one date would be counted twice by every limit."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    if body.dutydate > localnow(user["timezone"]).date():
        raise HTTPException(400, "That day has not happened yet")
    if body.drivingminutes < 0 or body.ondutyminutes < 0:
        raise HTTPException(400, "Hours cannot be negative")
    # Driving is time spent on duty, so it cannot exceed it. Recording 10 hours driving inside an
    # 8-hour duty day is a typing error, and letting it through would understate the duty total
    # every limit is measured from.
    if body.drivingminutes > body.ondutyminutes:
        raise HTTPException(400, "Driving time cannot be more than the on-duty time")
    if body.ondutyminutes > 24 * 60:
        raise HTTPException(400, "A day cannot hold more than 24 hours")
    run(conn, """
        INSERT INTO driverdutydays (recordid, accountid, driverid, dutydate, dutystart, dutyend,
                                    drivingminutes, ondutyminutes, source, note, enteredby)
        VALUES (:id, :a, :d, :on, :s, :e, :drv, :duty, 'manual', :n, :u)
        ON DUPLICATE KEY UPDATE dutystart = VALUES(dutystart), dutyend = VALUES(dutyend),
                                drivingminutes = VALUES(drivingminutes),
                                ondutyminutes = VALUES(ondutyminutes), note = VALUES(note),
                                deleted = NULL, updated = UTC_TIMESTAMP(),
                                enteredby = VALUES(enteredby)
    """, id=newid(), a=acct, d=driverid, on=body.dutydate, s=body.dutystart or None,
        e=body.dutyend or None, drv=body.drivingminutes, duty=body.ondutyminutes,
        n=(body.note or None), u=user["recordid"])
    log(conn, user, "duty-day", "driver", driverid,
        {"dutydate": str(body.dutydate), "driving": body.drivingminutes,
         "onduty": body.ondutyminutes}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "evaluation": evaluation}


@router.delete("/drivers/{driverid}/duty-days/{dutydate}")
def remove_duty_day(driverid: str, dutydate: date, request: Request, reason: str = "",
                    user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Take a day back off the record - a day entered against the wrong driver, or twice.

    A reason is required and kept. 49 CFR 395.8(k)(1) asks the carrier to keep records of duty
    status for six months, and a day that simply goes missing out of a driver's week - with the
    hours arithmetic quietly different afterwards - is a disappearance rather than a correction.
    """
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    why = (reason or "").strip()
    if len(why) < 3:
        raise HTTPException(400, "Say why this day is being withdrawn")
    n = run(conn, """
        UPDATE driverdutydays
           SET withdrawn = UTC_TIMESTAMP(), withdrawnby = :u, withdrawnreason = :r
        WHERE accountid = :a AND driverid = :d AND dutydate = :on
          AND deleted IS NULL AND withdrawn IS NULL
    """, a=acct, d=driverid, on=dutydate, u=user["recordid"], r=why[:255]).rowcount
    if not n:
        raise HTTPException(404, "No work is recorded for that day")
    log(conn, user, "duty-day-removed", "driver", driverid,
        {"dutydate": str(dutydate), "reason": why}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "evaluation": evaluation}


@router.get("/drivers/{driverid}/trips")
def driver_trips(driverid: str, user: dict = Depends(current_user),
                 conn: Connection = Depends(get_conn)):
    """What this driver has actually driven, newest first.

    A hired driver's file is not a hiring file any more. What was useful before they started -
    how far through the qualification they were - is answered, and what matters afterwards is the
    work: what they drove, when, and in what."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    trips = rows(conn, """
        SELECT t.recordid, t.externalid, t.tripdate, t.servicelevel, t.billingstatus,
               GROUP_CONCAT(DISTINCT COALESCE(v.externalid, v.vin) SEPARATOR ', ') AS vehicles,
               MIN(l.pickupat) AS startedat, MAX(l.dropoffat) AS finishedat,
               COUNT(l.recordid) AS legs,
               SUM(l.executionstate = 'completed') AS completed,
               SUM(l.executionstate IN ('enroute', 'arrived', 'onboard')) AS moving,
               SUM(l.outcomestate IS NOT NULL) AS closed,
               MAX(l.outcomestate) AS outcome
        FROM triplegs l
          JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
          LEFT JOIN vehicles v ON v.recordid = l.vehicleid AND v.deleted IS NULL
        WHERE l.accountid = :a AND l.driverid = :d
        GROUP BY t.recordid, t.externalid, t.tripdate, t.servicelevel, t.billingstatus
        ORDER BY t.tripdate DESC, t.externalid DESC
        LIMIT 100
    """, a=acct, d=driverid)
    # Where each trip stands, said, because the list holds what is coming as well as what was
    # driven - a canceled run and a completed one read the same without it.
    for t in trips:
        t["service"] = dispatch.SERVICE.get(t["servicelevel"] or "", {}).get("label") or t["servicelevel"]
        if t["completed"] and t["completed"] + t["closed"] >= t["legs"]:
            t["state"] = "completed"
        elif t["moving"]:
            t["state"] = "inprogress"
        elif t["closed"] >= t["legs"]:
            t["state"] = t["outcome"]
        else:
            t["state"] = "scheduled"
        for k in ("completed", "moving", "closed", "outcome"):
            t.pop(k)
    return {"trips": trips}
