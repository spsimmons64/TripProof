"""Fee schedules, Payers - who this company bills - moved out of routers/vault.py, which grew too large to work in safely.

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
    RANDOM_RATES,
)

router = APIRouter(prefix="/api", tags=["vault"])


# ------------------------------------------------------------------------------------------------
# Fee schedules - what this company charges, and what a payer contracts to pay it.
#
# Not to be confused with `feeschedule`, which is what TripProof charges ITS customers for
# pass-through services. Different money, different side of the business, different table.
# ------------------------------------------------------------------------------------------------

class RateIn(BaseModel):
    ratetype: str
    servicelevel: str | None = None
    unit: str = "trip"
    amount: float = 0
    includedunits: float | None = None
    minimumunits: float | None = None
    rounding: str | None = None
    proceduracode: str | None = None
    modifier: str | None = None
    authrequired: bool = False
    note: str | None = None
    # What this charge is called. Six surcharges on one schedule are otherwise six rows
    # reading "Surcharge".
    name: str | None = None
    # Mileage only: bill the miles with the passenger aboard, not the run out to fetch them.
    loadedonly: bool = False


class ScheduleIn(BaseModel):
    name: str
    # The schedule this one replaces, when it was opened by Supersede. The original is
    # given an end date the day before this one starts - and only here, as the replacement
    # is written, so a supersede that is cancelled leaves the live schedule alone.
    supersedes: str | None = None
    # 'private', or one payer category. A payer is offered only schedules of its own type.
    payertype: str | None = None
    contractref: str | None = None
    effectivefrom: date | None = None
    effectiveto: date | None = None
    note: str | None = None
    active: bool = True
    rates: list[RateIn] = []


@router.get("/company/rates")
def fee_schedules(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Every schedule this company holds, and the words the screen needs to describe them."""
    return {
        "schedules": rateset.schedules(conn, user["accountid"]),
        "ratetypes": rateset.RATE_TYPES, "units": rateset.UNITS,
        "services": rateset.SERVICES, "billing": rateset.BILLING,
        "rounding": rateset.ROUNDING,
        "categories": rateset.CATEGORIES,
        "categoryplural": rateset.CATEGORY_PLURAL,
        # The shared catalogue plus this company's own - a facility it contracts with is
        # nobody else's payer and is not in the platform list.
        "payers": rows(conn, """
            SELECT p.recordid, p.name, p.category FROM payers p
            LEFT JOIN accountpayers ap ON ap.payerid = p.recordid AND ap.accountid = :a
            WHERE COALESCE(ap.active, p.active) = 1 AND (p.accountid IS NULL OR p.accountid = :a)
            ORDER BY category, name
        """, a=user["accountid"]),
    }


@router.get("/company/rates/{scheduleid}")
def fee_schedule(scheduleid: str, user: dict = Depends(current_user),
                 conn: Connection = Depends(get_conn)):
    got = rateset.schedule(conn, user["accountid"], scheduleid)
    if not got:
        raise HTTPException(404, "No such fee schedule")
    return got


# -------------------------------------------------------------------------------------------
# Payers - who this company bills.
# -------------------------------------------------------------------------------------------

class PayerIn(BaseModel):
    name: str
    category: str = "commercial"
    code: str | None = None
    # How the clearinghouse names this payer, where it is billed electronically at all.
    payerid: str | None = None
    website: str | None = None
    notes: str | None = None
    active: bool = True
    # Where to write, and who to ring about a claim.
    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    phone: str | None = None
    fax: str | None = None
    contactname: str | None = None
    contactemail: str | None = None


def _own_payer(conn: Connection, accountid: str, payerrecordid: str) -> None:
    """A company edits its own payers and not the shared ones.

    The shared rows are the brokers TripProof publishes compliance rules against. A trip for
    one of them is checked against that broker's requirements, which holds only while every
    company points at the same row - so one company cannot rename or retire it for the rest.
    """
    held = row(conn, "SELECT accountid FROM payers WHERE recordid = :i", i=payerrecordid)
    if not held:
        raise HTTPException(404, "No such payer")
    if held["accountid"] != accountid:
        raise HTTPException(403, "That payer is part of the shared list and cannot be "
                                 "changed here")


@router.get("/company/payers")
def list_payers(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    # The service levels come back with them. A screen that books a trip has to offer exactly what
    # the fee schedule can price it at, and `rates.SERVICES` is read off `dispatch.SERVICE` - one
    # list, so a level added for pricing is bookable the same day.
    # With them, the company's lines - who it carries for, in which state, under which program
    # and contract - and what a line's dialog offers.
    from app.routers import operating
    return {"categories": rateset.CATEGORIES,
            "services": rateset.SERVICES,
            "payers": rateset.payers(conn, user["accountid"]),
            "lines": operating.lines(conn, user["accountid"]),
            "programs": operating.PROGRAMS,
            "categoryprograms": operating.CATEGORY_PROGRAMS,
            # What a payer, or one of its state lines, can be paid under - with its payer type,
            # so each is offered only its own.
            "schedules": [{**x, "kind": rateset.kind_of(x)} for x in rows(conn, """
                SELECT recordid, name, privatepay, payerkinds, effectivefrom, effectiveto
                FROM payerschedules WHERE accountid = :a AND active = 1 ORDER BY name
            """, a=user["accountid"])],
            "privatepayschedule": (row(conn, """
                SELECT scheduleid FROM accountpayers WHERE accountid = :a AND payerid = :p
            """, a=user["accountid"], p=rateset.PRIVATE) or {}).get("scheduleid"),
            "contractservices": list(operating.SERVICES),
            "catalog": rows(conn, "SELECT code, name FROM qualificationcatalog "
                                  "WHERE subject = 'driver' AND retiredon IS NULL ORDER BY sortorder")}


class PayerScheduleIn(BaseModel):
    scheduleid: str | None = None


@router.put("/company/payers/{payerrecordid}/schedule")
def payer_schedule(payerrecordid: str, body: PayerScheduleIn, request: Request,
                   user: dict = Depends(account_admin), conn: Connection = Depends(get_conn)):
    """The fee schedule this company is paid under by a payer, or by the passenger
    ('privatepay'). Kept as the company's own, a shared payer included."""
    acct = user["accountid"]
    if not body.scheduleid:
        raise HTTPException(400, "Choose the fee schedule")
    if payerrecordid == rateset.PRIVATE:
        kind = "private"
    else:
        held = row(conn, "SELECT category FROM payers WHERE recordid = :i "
                         "AND (accountid IS NULL OR accountid = :a)", i=payerrecordid, a=acct)
        if not held:
            raise HTTPException(404, "No such payer")
        kind = held["category"]
    try:
        rateset.set_payer_schedule(conn, acct, payerrecordid, kind, body.scheduleid,
                                   user["recordid"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    log(conn, user, "payer-schedule", "company", acct,
        {"payer": payerrecordid, "schedule": body.scheduleid}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class PayerStatusIn(BaseModel):
    active: bool
    # Who the company deals with there - its own, even at a shared payer.
    contactname: str | None = None
    contactemail: str | None = None


@router.put("/company/payers/{payerrecordid}/status")
def payer_status(payerrecordid: str, body: PayerStatusIn, request: Request,
                 user: dict = Depends(account_admin), conn: Connection = Depends(get_conn)):
    """Whether this company still works with a payer, and who it deals with there. For a shared one
    that is this company's own say, kept beside the payer; the payer itself, everybody's, is not
    touched."""
    acct = user["accountid"]
    held = row(conn, "SELECT accountid FROM payers WHERE recordid = :i "
                     "AND (accountid IS NULL OR accountid = :a)", i=payerrecordid, a=acct)
    if not held:
        raise HTTPException(404, "No such payer")
    who = {"cn": (body.contactname or "").strip().upper()[:128] or None,
           "ce": (body.contactemail or "").strip().lower()[:128] or None}
    if held["accountid"]:
        run(conn, """
            UPDATE payers SET active = :v, contactname = :cn, contactemail = :ce
            WHERE recordid = :i AND accountid = :a
        """, v=int(body.active), i=payerrecordid, a=acct, **who)
    else:
        run(conn, """
            INSERT INTO accountpayers (accountid, payerid, active, contactname, contactemail,
                                       updated, updatedby)
            VALUES (:a, :i, :v, :cn, :ce, :now, :u)
            ON DUPLICATE KEY UPDATE active = :v, contactname = :cn, contactemail = :ce,
                                    updated = :now, updatedby = :u
        """, a=acct, i=payerrecordid, v=int(body.active), now=utcnow(), u=user["recordid"],
            **who)
    log(conn, user, "payer-status", "company", acct,
        {"payer": payerrecordid, "active": body.active}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/company/payers")
def add_payer(body: PayerIn, request: Request, user: dict = Depends(account_admin),
              conn: Connection = Depends(get_conn)):
    if body.category not in rateset.CATEGORIES:
        raise HTTPException(400, f"Unknown payer kind {body.category}")
    if not body.name.strip():
        raise HTTPException(400, "A payer needs a name")
    pid = rateset.save_payer(conn, user["accountid"], body.model_dump())
    log(conn, user, "payer-added", "company", user["accountid"],
        {"payer": pid, "name": body.name}, ip=client_ip(request))
    saved(conn)
    return {"recordid": pid}


@router.put("/company/payers/{payerrecordid}")
def edit_payer(payerrecordid: str, body: PayerIn, request: Request,
               user: dict = Depends(account_admin), conn: Connection = Depends(get_conn)):
    if body.category not in rateset.CATEGORIES:
        raise HTTPException(400, f"Unknown payer kind {body.category}")
    _own_payer(conn, user["accountid"], payerrecordid)
    rateset.save_payer(conn, user["accountid"], body.model_dump(), payerrecordid)
    log(conn, user, "payer-changed", "company", user["accountid"], {"payer": payerrecordid},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.delete("/company/payers/{payerrecordid}")
def remove_payer(payerrecordid: str, request: Request, user: dict = Depends(account_admin),
                 conn: Connection = Depends(get_conn)):
    _own_payer(conn, user["accountid"], payerrecordid)
    # Refused rather than cascaded: a schedule or a trip pointing at a payer that has gone is
    # a price nobody can explain afterwards.
    using = rateset.payer_in_use(conn, user["accountid"], payerrecordid)
    if using:
        raise HTTPException(409, f"{using} schedule(s), trip(s) or state line(s) still name this payer. "
                                 "Make it inactive instead.")
    rateset.remove_payer(conn, user["accountid"], payerrecordid)
    log(conn, user, "payer-removed", "company", user["accountid"], {"payer": payerrecordid},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.get("/company/payers/{payerrecordid}/documents")
def payer_documents(payerrecordid: str, user: dict = Depends(account_admin),
                    conn: Connection = Depends(get_conn)):
    """What this company holds on file for this payer."""
    return rateset.documents(conn, user["accountid"], payerrecordid)


@router.post("/company/payers/{payerrecordid}/documents")
async def add_payer_document(
    payerrecordid: str,
    request: Request,
    title: str = Form(...),
    effectivefrom: date | None = Form(None),
    effectiveto: date | None = Form(None),
    note: str | None = Form(None),
    file: UploadFile = File(...),
    user: dict = Depends(account_admin),
    conn: Connection = Depends(get_conn),
):
    """File a contract, amendment, rate sheet or anything else against a payer.

    Filed against the company's own payers AND the shared ones: the contract is this
    company's, even where the payer is everybody's. What is forbidden is editing a shared
    payer's details, not having an arrangement with it.
    """
    acct = user["accountid"]
    if not row(conn, """
        SELECT 1 AS x FROM payers
        WHERE recordid = :i AND (accountid IS NULL OR accountid = :a)
    """, i=payerrecordid, a=acct):
        raise HTTPException(404, "No such payer")
    if not (title or "").strip():
        raise HTTPException(400, "Say what this document is")
    if effectiveto and effectivefrom and effectiveto < effectivefrom:
        raise HTTPException(400, "That contract ends before it starts")

    data = await file.read()
    if not data:
        raise HTTPException(400, "That file is empty")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "That file is larger than 20 MB")
    documentid = storage.keep(conn, acct, "payer", data, file.filename, file.content_type,
                              user["recordid"], origin="office")
    recordid = rateset.add_document(conn, acct, user["recordid"], payerrecordid, documentid,
                                    {"title": title, "effectivefrom": effectivefrom,
                                     "effectiveto": effectiveto, "note": note})
    log(conn, user, "payer-document-filed", "company", acct,
        {"payer": payerrecordid, "title": title}, ip=client_ip(request))
    saved(conn)
    return {"recordid": recordid}


@router.delete("/company/payers/{payerrecordid}/documents/{recordid}")
def remove_payer_document(payerrecordid: str, recordid: str, request: Request,
                          user: dict = Depends(account_admin),
                          conn: Connection = Depends(get_conn)):
    if not rateset.remove_document(conn, user["accountid"], recordid):
        raise HTTPException(404, "No such document")
    log(conn, user, "payer-document-removed", "company", user["accountid"],
        {"payer": payerrecordid}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


def _end_the_one_it_replaces(conn: Connection, accountid: str, body) -> None:
    """Close the schedule this one supersedes, the day before this one starts.

    Done before the overlap check, not after: the two would otherwise always collide - the
    old one runs to no end date and the new one starts inside it. Closing it first is what
    makes the pair legal, and doing it here means a supersede that is never saved never
    touches the live schedule.
    """
    if not body.supersedes:
        return
    old = row(conn, """
        SELECT recordid, name, effectivefrom, effectiveto, active FROM payerschedules
        WHERE recordid = :i AND accountid = :a
    """, i=body.supersedes, a=accountid)
    if not old:
        raise HTTPException(404, "No such fee schedule to replace")
    # A retired schedule governs nothing, so there is nothing to hand over. Ending it again
    # would stamp a date on something already out of use and leave the replacement looking
    # like the second half of a handover that never happened.
    if not old["active"]:
        raise HTTPException(409, f"{old['name']} is retired. Reinstate it to replace it, or "
                                 "copy it instead.")
    start = body.effectivefrom or date.today()
    if start <= old["effectivefrom"]:
        raise HTTPException(400, f"{old['name']} starts on "
                                 f"{old['effectivefrom']:%m/%d/%Y}. A schedule replacing it "
                                 "has to start after that.")
    # An open-ended schedule is simply closed the day before. One that ALREADY has an end
    # date is not moved: pulling it forward would silently extend or shorten a window
    # somebody set deliberately, and pushing the start out would leave days priced by
    # nothing at all. The two have to meet exactly.
    if old["effectiveto"] is not None:
        wanted = old["effectiveto"] + timedelta(days=1)
        if start != wanted:
            raise HTTPException(409,
                f"{old['name']} runs to {old['effectiveto']:%m/%d/%Y}, so its replacement "
                f"has to start on {wanted:%m/%d/%Y}. "
                + ("Starting later leaves days priced by nothing."
                   if start > wanted else "Starting earlier overlaps it."))
        return
    run(conn, """
        UPDATE payerschedules SET effectiveto = :end, updated = :now WHERE recordid = :i
    """, end=start - timedelta(days=1), now=utcnow(), i=old["recordid"])


def _payer_type(body) -> None:
    if body.payertype != "private" and body.payertype not in rateset.CATEGORIES:
        raise HTTPException(400, "Choose the payer type")


@router.post("/company/rates")
def add_fee_schedule(body: ScheduleIn, request: Request, user: dict = Depends(account_admin),
                     conn: Connection = Depends(get_conn)):
    """Write a schedule and its rate lines."""
    acct = user["accountid"]
    _end_the_one_it_replaces(conn, acct, body)
    # Payer is worked out from how it is billed and whether a broker is named - see
    # rates.save_schedule. How it is billed is the one of the two that must be answered:
    # unstated, there is no way to tell a Medicaid schedule from the private-pay prices.
    if body.effectiveto and body.effectivefrom and body.effectiveto < body.effectivefrom:
        raise HTTPException(400, "That schedule ends before it starts")
    _payer_type(body)
    scheduleid = rateset.save_schedule(conn, acct, user["recordid"], body.model_dump())
    rateset.save_rates(conn, acct, scheduleid, [r.model_dump() for r in body.rates])
    log(conn, user, "rates-added", "company", acct,
        {"schedule": scheduleid, "name": body.name}, ip=client_ip(request))
    saved(conn)
    return {"recordid": scheduleid}


@router.put("/company/rates/{scheduleid}")
def edit_fee_schedule(scheduleid: str, body: ScheduleIn, request: Request,
                      user: dict = Depends(account_admin),
                      conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    if not rateset.schedule(conn, acct, scheduleid):
        raise HTTPException(404, "No such fee schedule")
    if body.effectiveto and body.effectivefrom and body.effectiveto < body.effectivefrom:
        raise HTTPException(400, "That schedule ends before it starts")
    _payer_type(body)
    rateset.save_schedule(conn, acct, user["recordid"], body.model_dump(), scheduleid)
    rateset.save_rates(conn, acct, scheduleid, [r.model_dump() for r in body.rates])
    log(conn, user, "rates-changed", "company", acct, {"schedule": scheduleid},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class StandingIn(BaseModel):
    active: bool


@router.post("/company/rates/{scheduleid}/active")
def set_schedule_active(scheduleid: str, body: StandingIn, request: Request,
                        user: dict = Depends(account_admin),
                        conn: Connection = Depends(get_conn)):
    """Retire a schedule, or put it back.

    Both directions through one endpoint, because it is one flag. Which payers it prices is said
    on their lines, so bringing one back competes with nothing.
    """
    acct = user["accountid"]
    held = rateset.schedule(conn, acct, scheduleid)
    if not held:
        raise HTTPException(404, "No such fee schedule")
    rateset.set_active(conn, acct, scheduleid, body.active)
    log(conn, user, "rates-retired" if not body.active else "rates-reinstated",
        "company", acct, {"schedule": scheduleid}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.delete("/company/rates/{scheduleid}")
def retire_fee_schedule(scheduleid: str, request: Request,
                        user: dict = Depends(account_admin),
                        conn: Connection = Depends(get_conn)):
    """Take it out of use. Not deleted - a charge that cites it must still be explainable."""
    if not rateset.remove(conn, user["accountid"], scheduleid):
        raise HTTPException(404, "No such fee schedule")
    log(conn, user, "rates-retired", "company", user["accountid"], {"schedule": scheduleid},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.get("/company/mis-report")
def mis_report(year: int | None = None, user: dict = Depends(current_user),
               conn: Connection = Depends(get_conn)):
    """The figures for the drug and alcohol testing MIS report - 49 CFR 382.403.

    The preceding calendar year by default, because that is the year the form asks about: it is
    due by 15 March for the year before it, so somebody opening this in March wants last year
    and would have to think to ask for it."""
    acct = user["accountid"]
    today = localnow(user["timezone"]).date()
    return misreport.collect(conn, acct, year or (today.year - 1))


@router.get("/company/random-pool")
def random_pool_members(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Who is in the pool right now - the only names a draw may produce."""
    acct = user["accountid"]
    return {"drivers": rows(conn, """
        SELECT d.recordid,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS name,
               m.joinedon
        FROM randompoolmembership m JOIN drivers d ON d.recordid = m.driverid
        WHERE m.accountid = :a AND m.leftpoolon IS NULL AND d.deleted IS NULL
        ORDER BY d.lastname, d.firstname
    """, a=acct)}


@router.post("/company/random-selections")
async def record_random_selection(
    request: Request,
    drawnon: date = Form(...),
    testtype: str = Form(...),
    # Accepted and ignored. The pool size is counted from the membership on the day of the draw -
    # it used to be typed in beside a screen that was separately computing one, which is two
    # answers to one question on the same dialog. Kept in the signature so an older client
    # posting it gets a recorded draw rather than a 422.
    poolsize: int | None = Form(None),
    # Accepted and ignored, like poolsize: how many came out is how many were named.
    selected: int | None = Form(None),
    # The drivers the draw produced, as ids. This is the draw.
    drivers: list[str] = Form([]),
    performedby: str | None = Form(None),
    note: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: dict = Depends(account_admin),
    conn: Connection = Depends(get_conn),
):
    """Record a draw: the day, what it was for, the pool it came from and who made it."""
    acct = user["accountid"]
    if testtype not in RANDOM_RATES:
        raise HTTPException(400, "Say whether the draw was for controlled substances or alcohol")
    if drawnon > localnow(user["timezone"]).date():
        raise HTTPException(400, "That date has not happened yet")
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    # Counted on the day of the draw, and STORED rather than derived later. It is evidence of
    # what was actually drawn from: a driver who leaves the pool next March must not change what
    # last week's draw was made against, and recomputing history from today's membership would
    # do exactly that.
    counted = randompool.members_on(conn, acct, drawnon)
    # Only drivers who were actually in the pool on the day. A name that was not in the hat
    # cannot have come out of it, and letting one through would quietly make the selection
    # something other than random.
    inpool = [d for d in dict.fromkeys(drivers)
              if randompool.is_member(conn, acct, d, drawnon)]
    sid = newid()
    run(conn, """
        INSERT INTO randomselections (recordid, accountid, drawnon, testtype, poolsize, selected,
                                      performedby, documentid, note, addedby)
        VALUES (:id, :a, :on, :t, :p, :s, :by, :doc, :n, :u)
    """, id=sid, a=acct, on=drawnon, t=testtype, p=counted, s=len(inpool) or selected,
        by=(performedby or "").strip()[:160] or None, doc=documentid,
        n=(note or "").strip()[:512] or None, u=user["recordid"])
    randompool.select(conn, acct, sid, inpool, by=user["recordid"])
    log(conn, user, "random-selection", "company", acct,
        {"drawnon": str(drawnon), "testtype": testtype, "selected": selected},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.delete("/company/random-selections/{recordid}")
def remove_random_selection(recordid: str, request: Request, user: dict = Depends(account_admin),
                            conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    n = run(conn, """
        UPDATE randomselections SET deleted = :now
        WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, now=utcnow(), id=recordid, a=acct).rowcount
    if not n:
        raise HTTPException(404, "No such selection")
    log(conn, user, "random-selection-withdrawn", "company", acct, {"recordid": recordid},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}
