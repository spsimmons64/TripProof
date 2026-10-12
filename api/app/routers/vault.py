###################################################################################################
# The vault - drivers, vehicles, credentials, and the documents behind them.
#
# Any change to a credential re-evaluates exactly the trips it could affect (the holder's legs, or
# every trip for a company credential), so the exposure number is always current.
###################################################################################################
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

from app import (accidents, annualreview, applicationview, billing, certn, documents, drivers,
                 eligibility, emails, exposure,
                 employers, events, gfeview, hos, i9, misreport, pdfform, randompool,
                 roadtest, roadtestview,
                 mvr as mvrs,
                 facts as factset, formats, images, mailer, phi, rules, signatures, storage,
                 rates as rateset, vehicleclass, wheremap)
from app import gateways
from app.routers import signing, uploading
from app.activity import log
from app.config import settings
from app.db import get_conn, localnow, newid, row, rows, run, saved, utcnow
from app.evaluator import evaluate
from app.profiles import PROFILE_FIELDS, clean_profile
from app.routers import admin
from app.security import account_admin, client_ip, current_user, editor
from app.validity import credential_window

router = APIRouter(prefix="/api", tags=["vault"])

EXPIRING_DAYS = 30


def _status_today(c: dict, today: datetime) -> dict:
    """Coverage of one credential right now, using the type's own age limit (brokers may be stricter)."""
    exempt = bool(c.get("exempt"))
    w = credential_window(c["issuedon"], c["expireson"], c["revokedon"],
                          None if exempt else c["maxagedays"], 0,
                          None if exempt else c["defaultvaliddays"])
    if c["revokedon"] and c["revokedon"] <= today:
        state = "revoked"
    elif w.start > today:
        state = "future"
    elif w.end and w.end <= today:
        state = "expired"
    elif w.end and w.end <= today + timedelta(days=EXPIRING_DAYS):
        state = "expiring"
    else:
        state = "current"
    return {**c, "windowstart": w.start, "windowend": w.end, "endcode": w.endcode, "state": state}


def _credentials(conn: Connection, acct: str, subject: str, subjectid: str | None = None) -> list[dict]:
    extra = "AND c.subjectid = :sid" if subjectid else ""
    return rows(conn, f"""
        SELECT c.recordid, c.subject, c.subjectid, c.credentialtypeid, t.code AS typecode, t.name AS typename,
               t.maxagedays, t.defaultvaliddays, t.hasamount, c.number, c.issuer, c.amount, c.issuedon, c.expireson, c.revokedon, c.revokereason,
               c.supersedes, c.documentid, d.filename, c.notes, c.exempt, c.added
        FROM credentials c
        JOIN credentialtypes t ON t.recordid = c.credentialtypeid
        LEFT JOIN documents d ON d.recordid = c.documentid
        WHERE c.accountid = :a AND c.subject = :s AND c.deleted IS NULL {extra}
        ORDER BY t.name, c.issuedon DESC
    """, a=acct, s=subject, sid=subjectid)


def _latest_by_type(creds: list[dict], today: datetime) -> dict[str, dict]:
    """Per type, the credential that matters today: a covering one if any, else the newest."""
    out: dict[str, dict] = {}
    for c in (_status_today(c, today) for c in creds):
        cur = out.get(c["typecode"])
        rank = lambda x: (x["state"] in ("current", "expiring"), x["issuedon"])
        if cur is None or rank(c) > rank(cur):
            out[c["typecode"]] = c
    return out


def _exposure_by(conn: Connection, acct: str, subject: str) -> dict[str, dict]:
    """Trips put at risk by this holder's own credentials (not, say, the van they drove), each trip
    counted and summed once - the same attribution the dashboard uses."""
    return {r["sid"]: r for r in rows(conn, """
        SELECT x.subjectid AS sid, COUNT(*) AS trips, SUM(x.billedamount) AS amount
        FROM (SELECT DISTINCT c.subjectid, e.tripid, e.billedamount
              FROM tripexposure e
              JOIN legchecks c ON c.tripid = e.tripid AND c.runid = e.runid AND c.outcome <> 'pass'
              WHERE e.accountid = :a AND c.subject = :s AND c.subjectid IS NOT NULL) x
        GROUP BY x.subjectid
    """, a=acct, s=subject)}


def _mark_replaced(creds: list[dict]) -> list[dict]:
    """History view: a credential with a newer one of the same type is shown as replaced, not as an
    alarm - it still covers the trips it covered."""
    newest: dict[str, object] = {}
    for c in creds:
        if c["typecode"] not in newest or c["issuedon"] > newest[c["typecode"]]:
            newest[c["typecode"]] = c["issuedon"]
    for c in creds:
        if c["issuedon"] < newest[c["typecode"]] and c["state"] in ("expired", "current", "expiring"):
            c["state"] = "replaced"
    return creds


def _filed_here(conn: Connection, acct: str, driverid: str, sourcetable: str, sourceid: str,
                userid: str | None) -> None:
    """Somebody in this office put this record here, so they have read it.

    The counterpart to _came_in, and the reason the two exist is a distinction I had wrong: what
    decides whether to interrupt somebody is not who MADE the document but who DELIVERED it. A
    laboratory result typed in by the office was made outside and handled inside - the person
    filing it had it in front of them. Nothing happened while they were not looking, so there is
    nothing to announce and nobody left to check after them.

    Written at the moment of filing, in the same transaction, for the same reason the arrival is:
    the reading and the record are one act or the screen will disagree with itself."""
    run(conn, """
        INSERT INTO documentreads (recordid, accountid, subject, subjectid, sourcetable, sourceid,
                                   readby, note)
        VALUES (:id, :a, 'driver', :d, :t, :s, :u, 'Filed by the office.')
        ON DUPLICATE KEY UPDATE readon = CURRENT_TIMESTAMP, readby = VALUES(readby)
    """, id=newid(), a=acct, d=driverid, t=sourcetable, s=sourceid, u=userid)


def _came_in(conn: Connection, acct: str, driverid: str, code: str, what: str,
             sourcetable: str | None = None, sourceid: str | None = None) -> None:
    """Something has landed on this driver's file that nobody here was holding.

    A document down a public link, or an answer to something this office sent for. The office finds
    out it is there from the alert rather than by opening the driver, which is the whole point of
    raising one.

    Every filing path that records outside work calls this, and it is the only thing any of them
    has to remember. The needs-review state is not set here because it is not set anywhere: a rule
    whose evidence comes from outside is unread until `documentreads` says a person read it, so the
    record is in review from the instant it exists. The alert and the toast are written in the same
    transaction as the record. All three are true at the same moment or none of them are."""
    driver = row(conn, "SELECT firstname, lastname FROM drivers WHERE recordid = :d AND accountid = :a",
                 d=driverid, a=acct) or {}
    who = f'{driver.get("firstname") or ""} {driver.get("lastname") or ""}'.strip().title()
    # A record that is written over has to lose its reading with it. A licence row whose copy is
    # replaced, or an inquiry answered a second time, is new evidence wearing an old record's id,
    # and leaving the old reading in place would let it go green on something nobody has seen.
    if sourcetable and sourceid:
        run(conn, """
            DELETE FROM documentreads
            WHERE accountid = :a AND sourcetable = :t AND sourceid = :s
        """, a=acct, t=sourcetable, s=sourceid)
    events.arrived(conn, acct, driverid, code, f"{what} came in for {who}" if who else what)


def _close_read_arrivals(conn: Connection, acct: str, subject: str, subjectid: str) -> None:
    """Take out of the inbox anything this subject no longer has to be read for.

    The arrival and the needs-review state went in together and were meant to come out together.
    They did not: `read_arrivals` matched the arrival's own word for the thing - DOT_MEDICAL_CARD,
    PHI_ACK, DRIVER_LICENSE - against the REQUIREMENT's code - MEDICAL_CERT, PHI_CONFIDENTIALITY,
    DRIVER_LICENSE_COPY. Two vocabularies for one thing, so nothing ever matched and every
    document anybody read stayed in the queue for ever.

    So it stops matching words. The engine already knows whether anything about this subject is
    still waiting on a reading, and that is the only question worth asking: when nothing is, the
    inbox is empty for them, whatever each row happens to be called."""
    if subject != "driver":
        return
    waiting = any(
        i["status"] == "review"
        for i in rules.for_driver(conn, acct, subjectid,
                                  factset.assemble(conn, acct, subjectid)["facts"]))
    if not waiting:
        events.read_arrivals(conn, acct, "driver", subjectid)


def _reevaluate_subject(conn: Connection, user: dict, subject: str, subjectid: str):
    acct = user["accountid"]
    # Whatever brought us here changed this subject, so the feed hears about it here too.
    events.record(conn, acct, subject, subjectid)
    _close_read_arrivals(conn, acct, subject, subjectid)
    if subject == "company":
        tripids = None
    else:
        col = "driverid" if subject == "driver" else "vehicleid"
        tripids = [r["tripid"] for r in rows(conn, f"SELECT DISTINCT tripid FROM triplegs WHERE accountid = :a AND {col} = :s",
                                             a=acct, s=subjectid)]
    return evaluate(conn, acct, tripids, user["recordid"], "credential-change")


# ------------------------------------------------------------------------------------------------
# The company's own logins
#
# A company manages who at that company can sign in, without asking TripProof to do it. Everything
# here is scoped to the signed-in account: the account id is never taken from the request, so an
# owner cannot reach into another company's users however the call is shaped.
#
# The roles a company hands out are its own - owner, admin, staff, auditor - and never a platform
# role, which only TripProof staff hold and only TripProof can grant.
# ------------------------------------------------------------------------------------------------

ACCOUNT_ROLES = ("owner", "admin", "staff", "auditor")


class AccountUserIn(BaseModel):
    email: str
    name: str
    role: str = "staff"


class AccountUserPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    disabled: bool | None = None


def _theirs_to_manage(user: dict) -> None:
    """TripProof staff in a customer's portal can read this page and change nothing on it.

    Who may sign in at a company is the company's own decision, and a launched session is us
    standing in their office - not us being them. Without this, one wrong click from support closes
    the customer's owner and locks them out of their own account."""
    if user.get("platformrole"):
        raise HTTPException(403, "TripProof staff cannot change who signs in at a customer - "
                                 "the company manages its own users")


def _their_user(conn: Connection, accountid: str, userid: str) -> dict:
    held = row(conn, """
        SELECT recordid, email, name, role, platformrole, deleted FROM users
        WHERE recordid = :u AND accountid = :a
    """, u=userid, a=accountid)
    if not held:
        raise HTTPException(404, "No such user")
    if held["platformrole"]:
        # TripProof staff are not the company's to manage, even when they are sitting in its portal.
        raise HTTPException(403, "That login belongs to TripProof")
    return held


@router.get("/account/users")
def account_users(user: dict = Depends(account_admin), conn: Connection = Depends(get_conn)):
    """Who can sign in at this company, and whether they ever have."""
    used = ("EXISTS (SELECT 1 FROM activitylog l WHERE l.userid = u.recordid "
            "AND l.action IN ('password-set', 'login'))")
    return {"items": rows(conn, f"""
        SELECT u.recordid, u.email, u.name, u.role, u.lastlogin, u.added, u.deleted,
               {used} AS passwordset,
               -- 49 CFR 382.603. Who may call a reasonable suspicion test, and whether they
               -- have signed for the training that lets them - which is a different fact from
               -- somebody having recorded it about them.
               EXISTS (SELECT 1 FROM companyroles r WHERE r.accountid = u.accountid
                        AND r.userid = u.recordid AND r.role = 'supervisor'
                        AND r.until IS NULL) AS supervisor,
               (SELECT d.signedon FROM documentsignatures d
                 WHERE d.accountid = u.accountid AND d.ownertype = 'user'
                   AND d.ownerid = u.recordid
                   AND d.doctype = 'SUPERVISOR_TRAINING_RECORD') AS trainingsignedon
        FROM users u
        WHERE u.accountid = :a AND u.platformrole IS NULL
        ORDER BY u.deleted IS NOT NULL, u.name
    """, a=user["accountid"]), "me": user["recordid"]}


@router.post("/account/users")
def add_account_user(body: AccountUserIn, request: Request, tasks: BackgroundTasks,
                     user: dict = Depends(account_admin), conn: Connection = Depends(get_conn)):
    """Add a login and send its invitation. The login cannot be used until the invitation is."""
    _theirs_to_manage(user)
    if body.role not in ACCOUNT_ROLES:
        raise HTTPException(400, "Unknown role")
    made = admin._create_user(conn, user["accountid"], body.email, body.name.strip(), body.role,
                              None, user.get("timezone"))
    invited = admin._invite(conn, tasks, made["recordid"], "invite", user)
    log(conn, user, "account-add-user", "user", made["recordid"],
        {"email": made["email"], "role": body.role}, ip=client_ip(request))
    saved(conn)
    return {**made, "invitation": invited}


@router.patch("/account/users/{userid}")
def change_account_user(userid: str, body: AccountUserPatch, request: Request,
                        user: dict = Depends(account_admin), conn: Connection = Depends(get_conn)):
    """Rename them, change what they may do, or close the login.

    Nobody can close their own login or take away their own access: an account that locks out its
    last owner is an account that has to ring us."""
    _theirs_to_manage(user)
    held = _their_user(conn, user["accountid"], userid)
    if userid == user["recordid"] and (body.disabled or (body.role and body.role != held["role"])):
        raise HTTPException(400, "You cannot change your own access")
    if body.role and body.role not in ACCOUNT_ROLES:
        raise HTTPException(400, "Unknown role")
    # The last owner cannot be demoted or closed, by either route. A company that locks out its own
    # owner has nobody left who can let anybody back in.
    losing_owner = held["role"] == "owner" and not held["deleted"] and (
        (body.role and body.role != "owner") or body.disabled)
    if losing_owner:
        owners = row(conn, """
            SELECT COUNT(*) AS n FROM users
            WHERE accountid = :a AND role = 'owner' AND deleted IS NULL AND platformrole IS NULL
        """, a=user["accountid"])["n"]
        if owners <= 1:
            raise HTTPException(400, "Every company keeps at least one owner who can sign in")
    run(conn, """
        UPDATE users SET name = COALESCE(:n, name), role = COALESCE(:r, role),
               deleted = CASE WHEN :dis IS NULL THEN deleted WHEN :dis = 1 THEN UTC_TIMESTAMP() ELSE NULL END,
               updated = :now
        WHERE recordid = :u AND accountid = :a
    """, n=(body.name or "").strip() or None, r=body.role,
        dis=None if body.disabled is None else (1 if body.disabled else 0),
        now=utcnow(), u=userid, a=user["accountid"])
    log(conn, user, "account-change-user", "user", userid, body.model_dump(exclude_none=True),
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/account/users/{userid}/invite")
def invite_account_user(userid: str, request: Request, tasks: BackgroundTasks,
                        user: dict = Depends(account_admin), conn: Connection = Depends(get_conn)):
    """Send the invitation again - a link nobody used, or a password nobody remembers."""
    _theirs_to_manage(user)
    held = _their_user(conn, user["accountid"], userid)
    if held["deleted"]:
        raise HTTPException(400, "That login is closed")
    invited = admin._invite(conn, tasks, userid, "invite", user)
    log(conn, user, "account-invite-user", "user", userid, ip=client_ip(request))
    saved(conn)
    return invited


# ------------------------------------------------------------------------------------------------
# Credential types
# ------------------------------------------------------------------------------------------------

@router.get("/credentialtypes")
def credential_types(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    return rows(conn, """
        SELECT recordid, code, name, subject, category, maxagedays, defaultvaliddays, hasamount, description
        FROM credentialtypes WHERE active = 1 ORDER BY subject, category, name
    """)


# ------------------------------------------------------------------------------------------------
# Drivers
# ------------------------------------------------------------------------------------------------

class DriverIn(BaseModel):
    firstname: str
    lastname: str
    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    externalid: str | None = None
    dob: date | None = None
    licensenumber: str | None = None
    licensestate: str | None = None
    licensesince: date | None = None
    email: str | None = None
    phone: str | None = None
    emergencyname: str | None = None
    emergencyphone: str | None = None
    hiredon: date | None = None
    terminatedon: date | None = None
    # One ordered answer, because the three thresholds are nested and separate boxes could say
    # things that cannot be true - a CDL vehicle that is not a commercial motor vehicle.
    operation: str = "noncmv"           # noncmv | cmv | cdl | cdlheavy
    chapter1490: bool = False
    endorsementsneeded: str | None = None     # the letters the work requires: P, S, H, N, T, X
    # 391.11(b)(2), and three-valued: not assessed is not the same as assessed and failed.
    englishproficient: bool | None = None
    # Which drug and alcohol program governs this driver. Left unset it is worked out from how
    # they operate and what the company does - see eligibility.program - but a company under more
    # than one can say outright, and a positive result then invokes the right process.
    datprogram: str | None = None         # dot | ctd | broker | company
    randompoolon: date | None = None      # the day they went into the random testing pool


# "hired" rather than "active": active is what a record IS, hired is what happened to a person.
# How many rows a page may have before the standing is left off - see list_drivers.
GATE_ROWS = 100

DRIVER_STATUSES = ("application", "appcor", "new", "pending", "hired", "inactive", "declined")

# While a driver is in one of these, the application is their record: the office reads it, decides on
# it, and the driver is the only one who edits what it says. The editor is closed until then.
APPLYING = ("application", "appcor", "new")

# What a driver is being qualified to operate, in order. Nested rather than independent: a CDL
# vehicle is always a commercial motor vehicle, and anything 26,001 lb and over always needs a CDL.
OPERATION = ("noncmv", "cmv", "cdl", "cdlheavy")
DRIVER_SORTS = {"drivernumber": "d.drivernumber", "name": "d.lastname", "status": "d.status",
                "phone": "d.phone", "email": "d.email", "licenseclass": "d.licenseclass"}


@router.get("/drivers")
def list_drivers(q: str | None = None, status: str | None = None, sort: str = "name", dir: str = "asc",
                 page: int = 1, pagesize: int = 25,
                 user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """One page of drivers, filtered and sorted.

    `status` is one of the driver's own statuses: an application in progress, new (the applicant has
    finished and the office has not started), pending, active or inactive."""
    acct = user["accountid"]
    if status and status not in DRIVER_STATUSES:
        raise HTTPException(400, "Unknown status")
    pagesize = max(1, min(pagesize, 1000))
    page = max(page, 1)
    direction = "DESC" if dir.lower() == "desc" else "ASC"
    order_by = f"{DRIVER_SORTS.get(sort, 'd.lastname')} {direction}, d.lastname ASC, d.firstname ASC, d.recordid ASC"
    where = ["d.accountid = :a", "d.deleted IS NULL",
             "(:q IS NULL OR CONCAT_WS(' ', d.firstname, d.lastname, d.externalid, d.drivernumber,"
             " d.licensenumber) LIKE CONCAT('%', :q, '%'))",
             "(:s IS NULL OR d.status = :s)"]
    params = {"a": acct, "q": q or None, "s": status or None}
    clause = " AND ".join(where)
    total = row(conn, f"SELECT COUNT(*) AS n FROM drivers d WHERE {clause}", **params)["n"]
    items = rows(conn, f"""
        SELECT d.recordid, d.externalid, d.drivernumber, d.firstname, d.lastname, d.status,
               d.licensenumber, d.licensestate, d.licenseclass, d.endorsements,
               d.email, d.phone, d.hiredon, d.terminatedon, d.stub
        FROM drivers d WHERE {clause}
        ORDER BY {order_by}
        LIMIT :lim OFFSET :off
    """, lim=pagesize, off=(page - 1) * pagesize, **params)
    creds = _credentials(conn, acct, "driver")
    exposure = _exposure_by(conn, acct, "driver")
    today = localnow(user["timezone"])
    by_driver: dict[str, list] = {}
    for c in creds:
        by_driver.setdefault(c["subjectid"], []).append(c)
    for d in items:
        latest = _latest_by_type(by_driver.get(d["recordid"], []), today)
        d["credentials"] = len(latest)
        d["expired"] = sum(1 for c in latest.values() if c["state"] in ("expired", "revoked"))
        d["expiring"] = sum(1 for c in latest.values() if c["state"] == "expiring")
        e = exposure.get(d["recordid"])
        d["risktrips"] = e["trips"] if e else 0
        d["riskamount"] = e["amount"] if e else 0
    # Whether each one may drive at all, by the same gate the driver's own file uses. Worked out
    # rather than stored, because a second answer kept in a column is a second answer that can be
    # wrong - and the one place it must not be wrong is the list somebody picks a driver from.
    #
    # It costs a run of the engine per row, so it is bounded: a page somebody has asked to hold a
    # thousand drivers is not a page anybody is reading a status off, and an export must not take
    # a minute to answer.
    if len(items) <= GATE_ROWS:
        for d in items:
            gathered = factset.assemble(conn, acct, d["recordid"])
            gate = _gate(conn, acct, d["recordid"],
                         rules.for_driver(conn, acct, d["recordid"], gathered["facts"]),
                         gathered["facts"])
            d["candrive"] = gate["candrive"]
            d["disqualified"] = gate["disqualified"]
            d["stopcount"] = len(gate["stops"])
    return {"total": total, "page": page, "pagesize": pagesize, "items": items}


def _driver_phone(body: DriverIn):
    try:
        body.phone = formats.phone(body.phone)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/drivers")
def create_driver(body: DriverIn, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    _driver_phone(body)
    did = newid()
    run(conn, """
        INSERT INTO drivers (recordid, accountid, externalid, drivernumber, firstname, lastname, dob,
                             licensenumber, licensestate, licensesince, email, phone, hiredon, terminatedon)
        VALUES (:id, :a, :ext, :num, :f, :l, :dob, :lic, :ls, :lsince, :em, :ph, :h, :t)
    """, id=did, a=user["accountid"], ext=body.externalid or None,
        num=drivers.next_number(conn, user["accountid"]), f=body.firstname, l=body.lastname, dob=body.dob,
        lic=body.licensenumber, ls=body.licensestate, lsince=body.licensesince, em=body.email, ph=body.phone,
        h=body.hiredon, t=body.terminatedon)
    log(conn, user, "create", "driver", did)
    return {"recordid": did}


@router.get("/drivers/{driverid}")
def get_driver(driverid: str, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    d = row(conn, "SELECT * FROM drivers WHERE recordid = :id AND accountid = :a AND deleted IS NULL", id=driverid, a=acct)
    if not d:
        raise HTTPException(404, "Driver not found")
    today = localnow(user["timezone"])
    d["credentials"] = _mark_replaced([_status_today(c, today) for c in _credentials(conn, acct, "driver", driverid)])
    d["exposure"] = _exposure_by(conn, acct, "driver").get(driverid, {"trips": 0, "amount": 0})
    # The number itself stays sealed; the last four are what an office reads back to a driver on the
    # telephone, and they cannot be edited here - a wrong one is a TripProof matter, not a typo.
    # The ids of the driver credential types, so a screen can file one without a second round trip.
    d["credentialtypes"] = {r["code"]: r["recordid"] for r in rows(conn,
        "SELECT code, recordid FROM credentialtypes WHERE subject = 'driver' AND active = 1")}
    held = (phi.get(conn, acct, "driver", driverid) or {}).get("ssn")
    d["ssnlast4"] = held[-4:] if held and len(held) >= 4 else None
    d.pop("ssnhash", None)
    return d


@router.get("/drivers/{driverid}/application")
def driver_application(driverid: str, request: Request, user: dict = Depends(current_user),
                       conn: Connection = Depends(get_conn)):
    """The online application this driver filled in, as one page of HTML with every file they
    uploaded carried inside it."""
    view = applicationview.application_for(conn, user["accountid"], driverid)
    if not view:
        raise HTTPException(404, "This driver has no online application")
    log(conn, user, "view", "driverapplication", driverid, ip=client_ip(request))
    return view


class LicenseIn(BaseModel):
    number: str
    state: str
    classification: str | None = None
    endorsements: str | None = None
    issued: date | None = None
    expires: date | None = None
    active: bool = False
    note: str | None = None


def _licences(conn: Connection, accountid: str, driverid: str) -> list[dict]:
    """The licences on file, each saying whether this office still has to read its copy.

    The reading is asked of the engine with the same function the status is worked out from. This
    table is its own screen and does not go through the generic requirement list, so without this
    it had no idea a copy was waiting - the licence read "Review" on the requirements page and
    "View" with nothing behind it here."""
    held = rows(conn, """
        SELECT recordid, number, state, classification, endorsements, issued, expires, active, note,
               copydocumentid
        FROM driverlicenses WHERE accountid = :a AND driverid = :d
        ORDER BY active DESC, COALESCE(issued, '1900-01-01') DESC
    """, a=accountid, d=driverid)
    rule = row(conn, """
        SELECT origin FROM compliancerules
        WHERE subject = 'driver' AND code = 'DRIVER_LICENSE_COPY' AND effectiveto IS NULL
    """) or {"origin": "driver"}
    read = rules.already_read(conn, accountid, driverid)
    readdocs = rules.read_documents(conn, accountid, driverid)
    return [{**l, "needsreading": bool(l["copydocumentid"]) and rules.needs_reading(
                rule, {**l, "sourcetable": "driverlicenses", "documentid": l["copydocumentid"]},
                read, readdocs)}
            for l in held]


def _make_active(conn: Connection, accountid: str, driverid: str, licenceid: str) -> None:
    """One licence is the one they drive on, and every check reads it from the driver row - so the
    driver row is kept in step with whichever is marked."""
    run(conn, "UPDATE driverlicenses SET active = 0 WHERE accountid = :a AND driverid = :d",
        a=accountid, d=driverid)
    run(conn, "UPDATE driverlicenses SET active = 1, updated = :now WHERE recordid = :id AND accountid = :a",
        now=utcnow(), id=licenceid, a=accountid)
    held = row(conn, "SELECT number, state, classification, endorsements FROM driverlicenses WHERE recordid = :id",
               id=licenceid)
    if held:
        run(conn, """
            UPDATE drivers SET licensenumber = :n, licensestate = :s, licenseclass = :c,
                   endorsements = :e, updated = :now
            WHERE recordid = :d AND accountid = :a
        """, n=held["number"], s=held["state"], c=held["classification"], e=held["endorsements"],
            now=utcnow(), d=driverid, a=accountid)


@router.get("/drivers/{driverid}/licenses")
def driver_licences(driverid: str, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    _applicant(conn, user["accountid"], driverid)
    return {"licenses": _licences(conn, user["accountid"], driverid)}


LICENCE_COPY_NAME = "Copy Of Driver's License.pdf"


@router.post("/drivers/{driverid}/licenses/{licenseid}/copy")
async def file_licence_copy(
    driverid: str,
    licenseid: str,
    request: Request,
    front: UploadFile | None = File(None),
    back: UploadFile | None = File(None),
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    """The licence as one document: the front, then the back, bound into a single PDF.

    Photographs become pages on the way in - see app/images.py - so what the file ends up holding
    is the card, not two snapshots that have to be read together."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    lic = row(conn, """
        SELECT recordid FROM driverlicenses WHERE recordid = :l AND accountid = :a AND driverid = :d
    """, l=licenseid, a=acct, d=driverid)
    if not lic:
        raise HTTPException(404, "That licence is not on this driver")
    pages = []
    for side in (front, back):
        if side is None or not side.filename:
            continue
        data = await side.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        page, mimetype, _name = images.to_pdf(data, side.content_type, side.filename)
        if mimetype != "application/pdf":
            raise HTTPException(415, "Upload a photograph or a PDF")
        pages.append(page)
    if not pages:
        raise HTTPException(400, "Choose at least one side to file")
    documentid = storage.keep(conn, acct, "documents", images.bind(pages), LICENCE_COPY_NAME,
                              "application/pdf", user["recordid"], origin=storage.OFFICE)
    run(conn, "UPDATE driverlicenses SET copydocumentid = :doc, updated = :now WHERE recordid = :l",
        doc=documentid, now=utcnow(), l=licenseid)
    _filed_here(conn, acct, driverid, "driverlicenses", licenseid, user["recordid"])
    log(conn, user, "licencecopy", "driver", driverid, {"pages": len(pages)}, ip=client_ip(request))
    saved(conn)
    return {"ok": True, "documentid": documentid}


@router.post("/drivers/{driverid}/licenses")
def add_driver_licence(driverid: str, body: LicenseIn, request: Request,
                       user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    number = (body.number or "").strip().upper()
    state = (body.state or "").strip().upper()[:2]
    if not number or len(state) != 2:
        raise HTTPException(400, "A license number and state are required")
    held = row(conn, """
        SELECT recordid FROM driverlicenses WHERE accountid = :a AND driverid = :d AND state = :s AND number = :n
    """, a=acct, d=driverid, s=state, n=number)
    lid = held["recordid"] if held else newid()
    if held:
        run(conn, """
            UPDATE driverlicenses SET classification = :c, endorsements = :e, issued = :i, expires = :x,
                   note = :note, updated = :now WHERE recordid = :id
        """, c=body.classification, e=body.endorsements, i=body.issued, x=body.expires,
            note=body.note, now=utcnow(), id=lid)
    else:
        run(conn, """
            INSERT INTO driverlicenses (recordid, accountid, driverid, number, state, classification,
                                        endorsements, issued, expires, note)
            VALUES (:id, :a, :d, :n, :s, :c, :e, :i, :x, :note)
        """, id=lid, a=acct, d=driverid, n=number, s=state, c=body.classification,
            e=body.endorsements, i=body.issued, x=body.expires, note=body.note)
    # The first licence on file is the one they drive on until someone says otherwise.
    if body.active or not row(conn, "SELECT 1 AS x FROM driverlicenses WHERE accountid = :a AND driverid = :d AND active = 1",
                              a=acct, d=driverid):
        _make_active(conn, acct, driverid, lid)
    log(conn, user, "create", "driverlicense", driverid, {"state": state, "number": number}, ip=client_ip(request))
    out = _licences(conn, acct, driverid)
    saved(conn)
    # The id comes back as well as the list: a copy of the licence is filed against the licence it
    # belongs to, and the caller has just created it and has nothing else to identify it by.
    return {"recordid": lid, "licenses": out}


@router.post("/drivers/{driverid}/licenses/{licenseid}/active")
def activate_driver_licence(driverid: str, licenseid: str, request: Request,
                            user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Which licence this driver drives on. Every trip check reads the class and endorsements from
    the driver record, so marking one here is what moves them."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    if not row(conn, "SELECT 1 AS x FROM driverlicenses WHERE recordid = :id AND accountid = :a AND driverid = :d",
               id=licenseid, a=acct, d=driverid):
        raise HTTPException(404, "That license is not on this driver")
    _make_active(conn, acct, driverid, licenseid)
    log(conn, user, "update", "driverlicense", driverid, {"active": licenseid}, ip=client_ip(request))
    out = _licences(conn, acct, driverid)
    saved(conn)
    return {"licenses": out}


@router.delete("/drivers/{driverid}/licenses/{licenseid}")
def remove_driver_licence(driverid: str, licenseid: str, request: Request,
                          user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    held = row(conn, """
        SELECT active, state, number FROM driverlicenses
        WHERE recordid = :id AND accountid = :a AND driverid = :d
    """, id=licenseid, a=acct, d=driverid)
    if not held:
        raise HTTPException(404, "That license is not on this driver")
    if held["active"]:
        raise HTTPException(409, "That is the license this driver drives on. Make another one active first.")
    run(conn, "DELETE FROM driverlicenses WHERE recordid = :id", id=licenseid)
    log(conn, user, "delete", "driverlicense", driverid,
        {"state": held["state"], "number": held["number"]}, ip=client_ip(request))
    out = _licences(conn, acct, driverid)
    saved(conn)
    return {"licenses": out}


# ------------------------------------------------------------------------------------------------
# Drug and alcohol testing, and the bar that a violation puts on driving
#
# Kept apart from the rest of the file on purpose: everything else here asks whether a document is
# on hand, and this asks whether the driver may work at all. See app/eligibility.py.
# ------------------------------------------------------------------------------------------------

def _transit(conn: Connection, accountid: str) -> bool | None:
    """Whether this company works under a CTC, a transit contract or FDOT funding - the answer that
    pulls F.A.C. Chapter 41-2 and 14-90 in. Three-valued: unanswered is not "no"."""
    return factset.assemble(conn, accountid)["facts"].get("company.transit")


def _driver_for_rules(conn: Connection, accountid: str, driverid: str) -> dict:
    d = row(conn, """
        SELECT recordid, firstname, lastname, operatescmv, licenseclass, status, datprogram, hiredon
        FROM drivers WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=driverid, a=accountid)
    if not d:
        raise HTTPException(404, "No such driver")
    return d


@router.get("/drivers/{driverid}/testing")
def driver_testing(driverid: str, user: dict = Depends(current_user),
                   conn: Connection = Depends(get_conn)):
    """Every test on file, the bar in force if there is one, and what it would take to lift it."""
    acct = user["accountid"]
    driver = _driver_for_rules(conn, acct, driverid)
    held = eligibility.standing(conn, acct, driverid)
    under = eligibility.program(driver, _transit(conn, acct))
    # Random, post-accident and reasonable suspicion are things that happen to somebody who is
    # employed and driving.
    hired = bool(driver.get("hiredon")) or driver["status"] in ("hired", "inactive")
    offer = ["preemployment"]
    if hired:
        offer += ["random", "postaccident", "reasonablesuspicion"]
    # A return-to-duty test is the last step of a process somebody is actually in. Offering it to a
    # driver with no violation invites a test that answers nothing - 49 CFR 40.305 is about coming
    # back from a prohibition, and there is nothing to come back from.
    #
    # Nor is it the last step until the steps before it are done. Under Part 40 the test lifts the
    # bar only once a SAP has evaluated the driver and recorded that they completed what was
    # prescribed, so a collection taken before that changes nothing. Offering it anyway is how the
    # office came to file a negative return-to-duty test, watch the driver stay prohibited, and
    # have nothing on screen to say why. It is offered when it would mean something, and until
    # then the prohibition itself says what is owed first.
    if held and (held.get("sapcompliedon") or (held.get("program") or "dot") != "dot"):
        offer.append("returntoduty")
    # Follow-up testing exists because a SAP wrote a plan. No plan, no follow-up tests.
    if any(h.get("followuptests") for h in eligibility.history(conn, acct, driverid)):
        offer.append("followup")
    return {"covered": eligibility.covered(driver),
            # What a bar still owes, which is not only the way back: the SAP information is owed to
            # an applicant who will never work here, and the hiring decision is the company's own.
            "owed": eligibility.owed(held), "decisions": eligibility.DECISIONS,
            "program": under, "programs": eligibility.PROGRAMMES,
            "returntoduty": eligibility.RETURN_TO_DUTY.get(under),
            # Every reason, so a test already on file reads by its name whatever the driver's
            # standing is now, and the shorter list of what may be filed today.
            "results": eligibility.RESULTS, "reasons": eligibility.REASONS, "offer": offer,
            "prohibited": held, "history": eligibility.history(conn, acct, driverid),
            "tests": eligibility.tests(conn, acct, driverid),
            "preemployment": eligibility.preemployment_state(conn, acct, driverid)}


class WithdrawTestIn(BaseModel):
    reason: str


@router.post("/drivers/{driverid}/testing/tests/{testid}/withdraw")
def withdraw_drug_test(driverid: str, testid: str, body: WithdrawTestIn, request: Request,
                       user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Take back a test filed on the wrong driver, and undo everything it did.

    A reason is required and goes on the record. The correction is the kind of thing an auditor
    reads closely - a positive that leaves a file wants an explanation beside it - so there is
    nowhere in this to remove one silently."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    why = (body.reason or "").strip()
    if len(why) < 3:
        raise HTTPException(400, "Say why this test is being withdrawn")
    driver = _driver_for_rules(conn, acct, driverid)
    try:
        out = eligibility.withdraw(conn, acct, driverid, testid, reason=why,
                                   by=user["recordid"])
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    # Taking the bar off may put this driver back in the pool's way, and putting somebody back
    # on safety-sensitive work is not a decision this makes quietly - so it is only ever
    # reported, never done.
    out["poolnote"] = (None if randompool.is_member(conn, acct, driverid)
                       else "This driver is not in the random testing pool. If the bar was the "
                            "reason they came out, put them back from their own requirements.")
    log(conn, user, "test-withdrawn", "driver", driverid,
        {"testid": testid, "reason": why, "undone": out["undone"]}, ip=client_ip(request))
    _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "undone": out["undone"], "poolnote": out["poolnote"],
            "driver": f'{driver["firstname"]} {driver["lastname"]}'.strip()}


@router.get("/drivers/{driverid}/accidents")
def driver_accidents(driverid: str, user: dict = Depends(current_user),
                     conn: Connection = Depends(get_conn)):
    """The accident register for this driver, and for each one whether 382.303 owed a test."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    return {"accidents": accidents.for_driver(conn, acct, driverid),
            "windows": {"alcohol": 8, "drug": 32}}


@router.post("/drivers/{driverid}/accidents/{recordid}/withdraw")
def withdraw_accident(driverid: str, recordid: str, body: WithdrawTestIn, request: Request,
                      user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Take back an accident recorded against the wrong driver, with the reason kept.

    49 CFR 390.15(b) asks the carrier to keep the register for three years, so the row stays and
    is marked - an accident that vanishes out of a register is the one thing nobody can be shown
    an explanation for."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    why = (body.reason or "").strip()
    if len(why) < 3:
        raise HTTPException(400, "Say why this accident is being withdrawn")
    try:
        out = accidents.withdraw(conn, acct, driverid, recordid, reason=why,
                                 by=user["recordid"])
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    log(conn, user, "accident-withdrawn", "driver", driverid,
        {"recordid": recordid, "reason": why, "undone": out["undone"]}, ip=client_ip(request))
    _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "undone": out["undone"]}


@router.get("/accidents")
def company_accident_register(user: dict = Depends(current_user),
                              conn: Connection = Depends(get_conn)):
    """The register itself - 49 CFR 390.15(b) - across every driver.

    The per-driver view lives inside post-accident testing, because 382.303 is the reason to
    ask a driver's accidents. The REGISTER is a different thing addressed to the carrier, and
    it is one list: an auditor asking to see it is not asking to be walked through the roster
    one driver at a time."""
    acct = user["accountid"]
    kept = rows(conn, """
        SELECT a.recordid, a.driverid, a.occurredon, a.location, a.fatalities, a.injuries,
               a.hazmatreleased, a.note,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS driver
        FROM driveraccidents a LEFT JOIN drivers d ON d.recordid = a.driverid
        WHERE a.accountid = :a AND a.withdrawn IS NULL
        ORDER BY a.occurredon DESC, a.createdon DESC
    """, a=acct)
    # The particulars 390.15(b)(1) names, so the screen can say which are missing on which row
    # rather than only that the register as a whole is short.
    for x in kept:
        x["missing"] = [w for w, ok in (
            ("date", x["occurredon"]), ("where", (x["location"] or "").strip()),
            ("driver", x["driver"]), ("injured", x["injuries"] is not None),
            ("killed", x["fatalities"] is not None),
            ("hazmat", x["hazmatreleased"] is not None)) if not ok]
    return {"accidents": kept,
            # Only drivers on the roster. An accident is something that happened to somebody
            # who drives for this company, and offering an applicant who has never been behind
            # one of its wheels invites the wrong name onto a federal register.
            "drivers": rows(conn, """
                SELECT recordid, TRIM(CONCAT(firstname, ' ', lastname)) AS name
                FROM drivers WHERE accountid = :a AND deleted IS NULL AND status = 'hired'
                ORDER BY lastname, firstname""", a=acct)}


@router.post("/drivers/{driverid}/accidents")
def add_accident(driverid: str, request: Request, body: dict,
                 user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Write one accident up. It is written before anybody knows whether a citation was issued -
    that is the normal case, not an incomplete record - so every 382.303 answer may be left
    unanswered and filled in later."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    when = (body.get("occurredon") or "").strip()
    if not when:
        raise HTTPException(400, "Say when the accident happened")
    rid = accidents.record(
        conn, acct, driverid, occurredon=when.replace("T", " ")[:19],
        location=(body.get("location") or None), fatalities=body.get("fatalities"),
        injuries=body.get("injuries"), hazmatreleased=body.get("hazmatreleased"),
        injurytreatedaway=body.get("injurytreatedaway"), towaway=body.get("towaway"),
        cited=body.get("cited"), citedon=(body.get("citedon") or None),
        nottested=(body.get("nottested") or None), note=(body.get("note") or None),
        enteredby=user["recordid"])
    log(conn, user, "accident", "driver", driverid, {"occurredon": when}, ip=client_ip(request))
    saved(conn)
    return {"recordid": rid}


@router.post("/drivers/{driverid}/accidents/{recordid}")
def amend_accident(driverid: str, recordid: str, request: Request, body: dict,
                   user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Answer what was not known when it was written up - above all whether the driver was cited,
    which is the fact that decides whether a test was owed at all."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    held = accidents.one(conn, acct, recordid)
    if not held:
        raise HTTPException(404, "No such accident")
    accidents.amend(conn, acct, recordid, **body)
    log(conn, user, "accident-amended", "driver", driverid,
        {"recordid": recordid, "occurredon": str(held.get("occurredon") or "")},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/drivers/{driverid}/testing/tests")
async def file_drug_test(
    driverid: str,
    request: Request,
    reason: str = Form(...),
    collectedon: date = Form(...),
    result: str = Form(...),
    # What the MIS report is counted off - 49 CFR 382.403. The form is two halves, controlled
    # substances and alcohol, so a test that does not say which cannot be reported at all.
    testtype: str | None = Form(None),
    substance: str | None = Form(None),
    bac: float | None = Form(None),
    note: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    """File a test result. What follows from it follows automatically: a positive or a refusal bars
    the driver, and a negative return-to-duty test lifts that bar once the SAP has signed the
    driver off."""
    acct = user["accountid"]
    driver = _driver_for_rules(conn, acct, driverid)
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    try:
        out = eligibility.file_test(conn, acct, driverid, driver, reason=reason,
                                    collectedon=collectedon, result=result, documentid=documentid,
                                    note=note, enteredby=user["recordid"],
                                    transit=_transit(conn, acct),
                                    testtype=testtype, substance=substance, bac=bac)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _filed_here(conn, acct, driverid, "drugtests", out["recordid"], user["recordid"])
    log(conn, user, "drugtest", "driver", driverid,
        {"reason": reason, "result": result, "collectedon": str(collectedon)}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {**out, "evaluation": evaluation}


class ProhibitIn(BaseModel):
    source: str                              # clearinghouse | actualknowledge
    startedon: date
    note: str | None = None


@router.post("/drivers/{driverid}/testing/prohibit")
def prohibit_driver(driverid: str, body: ProhibitIn, request: Request,
                    user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Bar a driver without a test of our own - a Clearinghouse query that came back prohibited, or
    actual knowledge of a violation. Both bar the driver exactly as a positive test does."""
    acct = user["accountid"]
    driver = _driver_for_rules(conn, acct, driverid)
    if body.source not in ("clearinghouse", "actualknowledge"):
        raise HTTPException(400, "Say where this came from")
    if not eligibility.covered(driver):
        raise HTTPException(409, "Part 382 does not reach this driver")
    pid = eligibility.prohibit(conn, acct, driverid, source=body.source,
                               reason=eligibility.SOURCES[body.source], startedon=body.startedon,
                               note=body.note, enteredby=user["recordid"])
    if not pid:
        raise HTTPException(409, "This driver is already prohibited")
    log(conn, user, "prohibit", "driver", driverid, {"source": body.source}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "evaluation": evaluation}


@router.post("/drivers/{driverid}/testing/decision")
async def employment_decision(driverid: str, request: Request,
                              decision: str | None = Form(None),
                              sapinfogivenon: date | None = Form(None),
                              file: UploadFile | None = File(None),
                              user: dict = Depends(editor),
                              conn: Connection = Depends(get_conn)):
    """The employment decision after a violation, and the SAP information that is owed either way.

    These are deliberately one endpoint, because they are the two halves of the same moment and the
    second one is the one that gets forgotten. Neither touches the bar: DOT decides what the person
    may do, and nothing recorded here changes that.

    The list of SAPs is kept, not merely dated - 40.287 asks for the list to be given, and a date
    with nothing behind it is the employer's word for it."""
    acct = user["accountid"]
    _driver_for_rules(conn, acct, driverid)
    held = eligibility.standing(conn, acct, driverid)
    if not held:
        raise HTTPException(404, "This driver is not prohibited")
    decision = (decision or "").strip().lower() or None
    if decision and decision not in eligibility.DECISIONS:
        raise HTTPException(400, "Unknown employment decision")
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    # A list on file says it was given, so the date follows the document where none was typed.
    if documentid and not sapinfogivenon:
        sapinfogivenon = localnow(user["timezone"]).date()
    run(conn, """
        UPDATE driverprohibitions
           SET decision = COALESCE(:dec, decision),
               decidedon = CASE WHEN :dec IS NULL THEN decidedon ELSE CURDATE() END,
               decidedby = CASE WHEN :dec IS NULL THEN decidedby ELSE :u END,
               sapinfogivenon = COALESCE(:given, sapinfogivenon),
               sapinfogivenby = CASE WHEN :given IS NULL THEN sapinfogivenby ELSE :u END,
               sapinfodocumentid = COALESCE(:doc, sapinfodocumentid)
         WHERE recordid = :id AND accountid = :a
    """, dec=decision, given=sapinfogivenon, doc=documentid, u=user["recordid"],
        id=held["recordid"], a=acct)
    log(conn, user, "employment-decision", "driver", driverid,
        {"decision": decision, "sapinfogivenon": str(sapinfogivenon) if sapinfogivenon else None},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.put("/drivers/{driverid}/testing/prohibition")
async def update_prohibition(driverid: str, request: Request,
                             sapname: str | None = Form(None),
                             sapevaluatedon: date | None = Form(None),
                             sapcompliedon: date | None = Form(None),
                             followuptests: int | None = Form(None),
                             followupuntil: date | None = Form(None),
                             note: str | None = Form(None),
                             file: UploadFile | None = File(None),
                             user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """The return-to-duty process as it goes along: who the SAP is, when they evaluated the driver,
    when the driver completed what was prescribed, and the follow-up testing plan that will outlive
    the prohibition. None of this lifts the bar - only a negative return-to-duty test does."""
    acct = user["accountid"]
    _driver_for_rules(conn, acct, driverid)
    held = eligibility.standing(conn, acct, driverid)
    if not held:
        raise HTTPException(404, "This driver is not prohibited")
    if sapcompliedon and not (sapevaluatedon or held["sapevaluatedon"]):
        raise HTTPException(400, "Record the evaluation before the driver's compliance with it")
    # A date with nothing behind it is somebody's word for it, so the determination itself is kept.
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    run(conn, """
        UPDATE driverprohibitions SET sapname = COALESCE(:n, sapname),
               sapevaluatedon = COALESCE(:ev, sapevaluatedon),
               sapcompliedon = COALESCE(:co, sapcompliedon),
               followuptests = COALESCE(:ft, followuptests),
               followupuntil = COALESCE(:fu, followupuntil),
               documentid = COALESCE(:doc, documentid),
               note = COALESCE(:note, note)
        WHERE recordid = :id
    """, n=sapname, ev=sapevaluatedon, co=sapcompliedon, ft=followuptests,
        fu=followupuntil, doc=documentid, note=note, id=held["recordid"])
    log(conn, user, "rtd", "driver", driverid,
        {"sapname": sapname, "sapevaluatedon": str(sapevaluatedon or ""),
         "sapcompliedon": str(sapcompliedon or "")}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


# ------------------------------------------------------------------------------------------------
# The other reports the office sends away for
#
# A PSP report and a CDLIS check are each one report about one driver, not one per licence: the
# FMCSA holds a single crash and inspection history, and CDLIS answers a single question about
# licences held anywhere. They are ordered, received and read the same way a driving record is, so
# they are worked the same way - and the screening on the driver's list reads whichever is current.
# ------------------------------------------------------------------------------------------------

REPORTS = {
    "PSP_REPORT": "PSP Report",
    "CDLIS_CHECK": "CDLIS Report",
    "CLEARINGHOUSE_PREEMP": "Clearinghouse Query",
    "BACKGROUND_SCREENING": "Background Check",
}

# What can be ordered, and what it costs. Held here rather than in the rule row because a price is
# ours and changes on our terms, while the requirement is the company's contract and does not.
# The tier is recorded on the order: a Core search that came back clear is not evidence that a
# Complete one would have, and "what did you actually run on this driver" is a question an auditor
# asks.
SCREENING_TIERS = {
    "core": {"name": "Core Background Check", "price": 2399,
             "covers": "National criminal database and sex offender registry searches."},
    "complete": {"name": "Complete Background Check", "price": 5999,
                 "covers": "Everything in Core, plus county and federal criminal searches and "
                           "identity verification."},
}

# What a report can come back saying. Most of these are a reader's judgement - somebody read the
# crash history and decided it needed a second look - so the words are deliberately vague.
#
# A Clearinghouse query is not like that. It asks one question and returns one of two answers, and
# the answer is the FMCSA's, not the reader's. "Prohibited" there is not an opinion about a report;
# it is a fact with a consequence - 49 CFR 382.701(a) does not permit the driver to perform
# safety-sensitive functions - so it carries its own words and its own effect.
DEFAULT_OUTCOMES = {"clear": "Clear", "review": "Needs a look", "flagged": "Adverse"}
# Read as a finding, not as a grade: somebody opens the query result and determines whether this
# driver may drive. The words are the question being answered, which is why they are not the
# reader's-opinion words the other reports use.
REPORT_OUTCOMES = {
    "CLEARINGHOUSE_PREEMP": {
        "qualified": "Qualified to drive",
        "prohibited": "Prohibited - may not perform safety-sensitive functions",
    },
}
# Filing one by hand IS reading one: whoever uploads the result has it open in front of them, and
# the finding they pick is that reading. A response to an ORDER is the opposite - it arrived
# because somebody asked for it days ago and nobody has looked at it yet - so it lands unread and
# the requirement waits on somebody reading it.


def _outcomes(code: str) -> dict:
    return REPORT_OUTCOMES.get(code, DEFAULT_OUTCOMES)


def _report_code(code: str) -> str:
    if code not in REPORTS:
        raise HTTPException(404, "No such report")
    return code


def _report_stage(r: dict) -> str:
    """Where one report has got to. A report on file has either been read or it has not - what it
    says is in the report, and the office reads it there rather than in a box somebody typed."""
    if not r["receivedon"]:
        return "ordered"
    return "reviewed" if r["reviewstate"] == "reviewed" else "pending"


@router.get("/drivers/{driverid}/reports/{code}")
def driver_reports(driverid: str, code: str, user: dict = Depends(current_user),
                   conn: Connection = Depends(get_conn)):
    """This report for this driver - what has been sent for, and what has come back."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    _report_code(code)
    held = rows(conn, """
        SELECT r.recordid, r.orderedon, r.issuedon, r.receivedon, r.outcome, r.reviewstate,
               r.reviewedon, r.note, r.documentid, d.filename, d.bytes
        FROM driverreports r
        LEFT JOIN documents d ON d.recordid = r.documentid AND d.deleted IS NULL
        WHERE r.accountid = :a AND r.driverid = :d AND r.code = :c
        ORDER BY COALESCE(r.issuedon, DATE(r.orderedon)) DESC, r.createdon DESC
    """, a=acct, d=driverid, c=code)
    # How long one of these stands is the rule's own arithmetic, not this screen's. A Clearinghouse
    # query is good for a year (49 CFR 382.701(b)); a PSP report has no horizon at all. Reading the
    # recurrence off the rule means the table and the engine can never disagree about the date.
    rule = row(conn, """
        SELECT recurrence, recurrencedays FROM compliancerules
        WHERE subject = 'driver' AND evidencesource = :src AND effectiveto IS NULL
          AND (accountid IS NULL OR accountid = :a) LIMIT 1
    """, src=f"report:{code}", a=acct)
    span = (rule or {}).get("recurrencedays") if (rule or {}).get("recurrence") == "days" else None
    for r in held:
        r["state"] = _report_stage(r)
        r["expireson"] = (r["issuedon"] + timedelta(days=int(span))
                          if span and r["issuedon"] else None)
    # Only what stands now, as with a driving record: the earlier ones are kept and read in the
    # driver's file, but they are not what the office is waiting on.
    # The whole history, the way a licence shows every driving record pulled on it. The earlier
    # ones are not what the office is waiting on, but they are part of the file.
    return {"code": code, "name": REPORTS[code], "reports": held, "outcomes": _outcomes(code)}


class ReportOrderIn(BaseModel):
    note: str | None = None


@router.post("/drivers/{driverid}/reports/{code}/order")
def order_report(driverid: str, code: str, body: ReportOrderIn, request: Request,
                 user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Send for it. TripProof does not pull it - the office does, at the source - so this records
    who asked and when, and starts the clock."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    _report_code(code)
    waiting = row(conn, """
        SELECT recordid, receivedon FROM driverreports
        WHERE accountid = :a AND driverid = :d AND code = :c AND receivedon IS NULL LIMIT 1
    """, a=acct, d=driverid, c=code)
    if waiting:
        raise HTTPException(409, f"A {REPORTS[code]} is already on order for this driver")
    run(conn, """
        INSERT INTO driverreports (recordid, accountid, driverid, code, orderedon, orderedby, note)
        VALUES (:id, :a, :d, :c, :now, :u, :n)
    """, id=newid(), a=acct, d=driverid, c=code, now=utcnow(), u=user["recordid"],
        n=(body.note or "").strip() or None)
    log(conn, user, "order", "driverreport", driverid, {"code": code}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/drivers/{driverid}/reports/{code}")
async def file_report(
    driverid: str,
    code: str,
    request: Request,
    issuedon: date = Form(...),
    outcome: str | None = Form(None),
    note: str | None = Form(None),
    reportid: str | None = Form(None),       # filling an order already placed
    file: UploadFile | None = File(None),
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    """File what came back: the date the report itself carries, and the report."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    _report_code(code)
    if file is None or not file.filename:
        raise HTTPException(400, "Attach the report")
    if outcome and outcome not in _outcomes(code):
        raise HTTPException(400, "Unknown outcome")
    waiting = row(conn, """
        SELECT recordid FROM driverreports WHERE accountid = :a AND driverid = :d AND code = :c
          AND receivedon IS NULL ORDER BY orderedon LIMIT 1
    """, a=acct, d=driverid, c=code)
    # Filling an order: the answer somebody sent for has come back, and has been read by nobody.
    fills_order = bool(waiting) and (not reportid or reportid == waiting["recordid"])
    if fills_order:
        outcome = None
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    outstanding = row(conn, """
        SELECT recordid FROM driverreports WHERE accountid = :a AND driverid = :d AND code = :c
          AND receivedon IS NULL AND (:r IS NULL OR recordid = :r) ORDER BY orderedon LIMIT 1
    """, a=acct, d=driverid, c=code, r=reportid)

    now = utcnow()
    filedid = None               # set only where a new row is written rather than an order filled
    if outstanding:
        run(conn, """
            UPDATE driverreports SET issuedon = :on, receivedon = :now, receivedby = :u,
                   documentid = :doc, outcome = :o, note = COALESCE(:n, note),
                   reviewstate = :rs,
                   reviewedon = CASE WHEN :rs = 'reviewed' THEN :now ELSE NULL END,
                   reviewedby = CASE WHEN :rs = 'reviewed' THEN :u ELSE NULL END
            WHERE recordid = :id
        """, on=issuedon, now=now, u=user["recordid"], doc=documentid, o=outcome,
            rs=("pending" if fills_order else "reviewed"),
            n=(note or None), id=outstanding["recordid"])
    else:
        filedid = newid()
        run(conn, """
            INSERT INTO driverreports (recordid, accountid, driverid, code, issuedon, receivedon,
                                       receivedby, documentid, outcome, note, reviewstate,
                                       reviewedon, reviewedby)
            VALUES (:id, :a, :d, :c, :on, :now, :u, :doc, :o, :n, 'reviewed', :now, :u)
        """, id=filedid, a=acct, d=driverid, c=code, on=issuedon, now=now, u=user["recordid"],
            doc=documentid, o=outcome, n=(note or None))
    # 49 CFR 382.701(a): a driver the Clearinghouse shows prohibited may not perform safety-
    # sensitive functions. Nothing here lifts a bar - only the return-to-duty process does.
    if code == "CLEARINGHOUSE_PREEMP" and outcome == "prohibited" and not fills_order:
        driver = _driver_for_rules(conn, acct, driverid)
        under = eligibility.program(driver, _transit(conn, acct)) or "dot"
        eligibility.prohibit(
            conn, acct, driverid, source="clearinghouse", program=under,
            reason=f"The FMCSA Clearinghouse shows this driver prohibited "
                   f"(query of {issuedon:%m/%d/%Y})",
            startedon=issuedon, enteredby=user["recordid"])
    # An answer to something sent for is work arriving, not work done: nobody has read it, and the
    # office finds out it is there from the inbox rather than by opening the driver again. The
    # `report-returned` kind was already carried into the inbox and nothing had ever raised it.
    if fills_order:
        _came_in(conn, acct, driverid, code, REPORTS[code],
                 "driverreports", outstanding["recordid"])
    else:
        _filed_here(conn, acct, driverid, "driverreports",
                    (outstanding or {}).get("recordid") or filedid, user["recordid"])
    log(conn, user, "file", "driverreport", driverid,
        {"code": code, "issuedon": str(issuedon), "outcome": outcome}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "evaluation": evaluation}


class ReportReviewIn(BaseModel):
    finding: str
    note: str | None = None


@router.post("/drivers/{driverid}/reports/{code}/{reportid}/reviewed")
def mark_report_reviewed(driverid: str, code: str, reportid: str, body: ReportReviewIn,
                         request: Request, user: dict = Depends(editor),
                         conn: Connection = Depends(get_conn)):
    """Somebody has read the query result and determined what it means.

    The same act as reading a driving record: the document is on file either way, and what the
    office concluded from it is a separate thing somebody puts their name to. For a Clearinghouse
    query the conclusion has teeth - 49 CFR 382.701(a) does not permit a prohibited driver to
    perform safety-sensitive functions, so finding them prohibited bars them here and now."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    _report_code(code)
    held = row(conn, """
        SELECT recordid, receivedon, issuedon FROM driverreports
        WHERE recordid = :r AND accountid = :a AND driverid = :d AND code = :c
    """, r=reportid, a=acct, d=driverid, c=code)
    if not held:
        raise HTTPException(404, "No such report")
    if not held["receivedon"]:
        raise HTTPException(409, "That one has not come back yet")
    finding = (body.finding or "").strip()
    if finding not in _outcomes(code):
        raise HTTPException(400, "Say what reading it concluded")
    run(conn, """
        UPDATE driverreports SET outcome = :o, reviewstate = 'reviewed', reviewedon = :now,
               reviewedby = :u, note = COALESCE(:n, note)
        WHERE recordid = :r
    """, o=finding, now=utcnow(), u=user["recordid"], n=(body.note or "").strip() or None,
        r=reportid)
    # Nothing here lifts a bar - only the return-to-duty process does - but a reading that finds
    # the driver prohibited puts one on.
    if finding == "prohibited":
        driver = _driver_for_rules(conn, acct, driverid)
        under = eligibility.program(driver, _transit(conn, acct)) or "dot"
        started = held["issuedon"] or localnow(user["timezone"]).date()
        eligibility.prohibit(
            conn, acct, driverid, source="clearinghouse", program=under,
            reason=f"The FMCSA Clearinghouse shows this driver prohibited "
                   f"(query of {started:%m/%d/%Y})",
            startedon=started, enteredby=user["recordid"])
    log(conn, user, "reviewed", "driverreport", driverid,
        {"code": code, "reportid": reportid, "finding": finding}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "evaluation": evaluation}


@router.delete("/drivers/{driverid}/reports/{code}/{reportid}")
def cancel_report_order(driverid: str, code: str, reportid: str, request: Request,
                        user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Take back an order placed by mistake. A report already filed is not removed here."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    _report_code(code)
    held = row(conn, """
        SELECT recordid, receivedon FROM driverreports
        WHERE recordid = :r AND accountid = :a AND driverid = :d AND code = :c
    """, r=reportid, a=acct, d=driverid, c=code)
    if not held:
        raise HTTPException(404, "No such order")
    if held["receivedon"]:
        raise HTTPException(409, "That report is on file")
    run(conn, "DELETE FROM driverreports WHERE recordid = :r", r=reportid)
    log(conn, user, "cancel", "driverreport", driverid, {"code": code}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


# ------------------------------------------------------------------------------------------------
# Driving records, by licence
#
# A driving record is a state's account of one licence. A driver holding licences in two states has
# two histories, and pulling one is not pulling the other - so records are ordered, filed and read
# against the licence they belong to.
# ------------------------------------------------------------------------------------------------

def _unfinished_mvr(conn: Connection, accountid: str, licenseid: str) -> dict | None:
    """A request on this licence that has not come back yet.

    Only one thing genuinely cannot be allowed twice: two requests out to the same authority at
    once, because nothing afterwards says which answer belongs to which request.

    A record already ON FILE is no reason to refuse another. Records are pulled again - to check on
    somebody, to refresh one that has aged, because the annual came round - and refusing that would
    make monitoring impossible. This used to also block on a record nobody had read and on an annual
    review that was not complete, the second of which stopped working entirely when the annual review
    stopped belonging to a single record: the join found nothing, `r.finding IS NULL` was true of
    everything, and every licence was blocked from ever being asked about again."""
    return row(conn, """
        SELECT recordid, issuedon, receivedon, reviewstate
        FROM drivermvrs
        WHERE accountid = :a AND licenseid = :l AND orderedon IS NOT NULL AND receivedon IS NULL
          AND cancelledon IS NULL
        ORDER BY orderedon LIMIT 1
    """, a=accountid, l=licenseid)


def _blocked_by(mvr: dict) -> str:
    return "A driving record is already on order for this license"


def _mvr_type(conn: Connection) -> str:
    return row(conn, "SELECT recordid FROM credentialtypes WHERE code = 'MVR'")["recordid"]


@router.get("/drivers/{driverid}/mvrs")
def driver_mvrs(driverid: str, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Every licence this driver holds, and the driving records pulled on each - newest first, with
    anything still outstanding at the top of its licence."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    licences = _licences(conn, acct, driverid)
    held = rows(conn, """
        SELECT m.recordid, m.licenseid, m.orderedon, m.issuedon, m.receivedon, m.documentid, m.note,
               m.reviewstate, m.reviewedon, m.selfcert, m.medcertstatus, m.medcertexpires,
               m.medvariancetype, m.medvariance, d.filename, d.bytes, u.name AS orderedbyname
        FROM drivermvrs m
        LEFT JOIN documents d ON d.recordid = m.documentid AND d.deleted IS NULL
        LEFT JOIN users u ON u.recordid = m.orderedby
        WHERE m.accountid = :a AND m.driverid = :d
        ORDER BY COALESCE(m.issuedon, DATE(m.orderedon)) DESC, m.createdon DESC
    """, a=acct, d=driverid)
    reviews = {r["mvrid"]: r for r in rows(conn, """
        SELECT mvrid, recordid, reviewedon, finding, method, reviewer, documentid
        FROM annualreviews WHERE accountid = :a AND driverid = :d AND mvrid IS NOT NULL
        ORDER BY reviewedon, createdon
    """, a=acct, d=driverid)}
    by_licence: dict[str, list] = {}
    for m in held:
        m["review"] = reviews.get(m["recordid"])
        m["state"] = _mvr_stage(m)
        by_licence.setdefault(m["licenseid"], []).append(m)
    # Nothing says how long a driving record stands any more - that was a catalog answer, and the
    # catalog is gone until the requirements engine replaces it.
    maxdays = None
    for lic in licences:
        held = by_licence.get(lic["recordid"], [])
        lic["standing"] = _licence_standing(held, maxdays)
        # Only what stands now. A record received replaces the one before it: the earlier ones are
        # kept, and are read in the driver's file, but they are not what this licence is waiting on.
        lic["mvrs"] = held[:1]
        # One record at a time: while one is unresolved, another cannot be sent for or filed.
        waiting = _unfinished_mvr(conn, acct, lic["recordid"])
        lic["waiting"] = _blocked_by(waiting) if waiting else None
    return {"licenses": licences, "maxdays": maxdays,
            # Named here so the screen does not keep its own copy of either list.
            "selfcerts": SELF_CERT, "medcertstatuses": MED_CERT_STATUS}


# Where one driving record has got to. Having a record is the beginning of the chain, not the end
# of it: it has to be read, and the reading has to reach a finding.
def _mvr_stage(m: dict) -> str:
    if not m["receivedon"]:
        return "ordered"
    if m["reviewstate"] != "reviewed":
        return "pending"                 # on file, nobody has read it
    review = m.get("review")
    if not review or not review["finding"]:
        return "due"                     # read, and the annual review it owes is not complete
    return "qualified" if review["finding"] == "qualified" else "disqualified"


STANDING = {
    "none": "No driving record on file",
    "ordered": "Driving record ordered",
    "stale": "The driving record on file is out of date",
    "pending": "Driving record awaiting review",
    "due": "Annual review due",
    "qualified": "Qualified",
    "disqualified": "Disqualified",
}


def _licence_standing(mvrs: list[dict], maxdays: int | None) -> dict:
    """Where one licence stands. A licence is compliant only at the end of the chain - a current
    record, read, reviewed, and the review finding the driver qualified."""
    filed = [m for m in mvrs if m["receivedon"]]
    if not filed:
        state = "ordered" if mvrs else "none"
        return {"state": state, "says": STANDING[state]}
    newest = filed[0]                    # the listing is newest first
    if maxdays and newest["issuedon"] and (date.today() - newest["issuedon"]).days > maxdays:
        return {"state": "stale", "says": STANDING["stale"]}
    return {"state": newest["state"], "says": STANDING[newest["state"]]}


# What reading a driving record concludes. Kept apart from the annual review's finding: this is the
# disposition of one record, and a disqualifying one bites the moment it is recorded.
# How a CDL holder certified the kind of commercial driving they do. The State carries medical
# certification status only for the first of these; the other three are certified as not needing
# it, and for them the certificate in the office's own file is what governs.
SELF_CERT = {
    "NI": "Non-excepted interstate",
    "EI": "Excepted interstate",
    "NA": "Non-excepted intrastate",
    "EA": "Excepted intrastate",
}
# What the driving record says about medical qualification. "Not shown" is its own answer and not
# an absence: a record that does not carry the information has not told you the driver is fine.
MED_CERT_STATUS = {
    "certified": "Certified",
    "notcertified": "Not certified",
    "notshown": "Not shown on this record",
}
# The two ways a driver is medically qualified while not meeting a standard in 391.41. Offered as a
# choice because they are a closed set, and a free text box nobody knows how to fill is a box that
# gets filled differently by every person who meets it.
MED_VARIANCE = {
    "spe": "Skill Performance Evaluation certificate (391.49)",
    "exemption": "Federal exemption (vision, diabetes, hearing, seizure)",
}

MVR_FINDINGS = {
    "qualified": "Nothing on the record affects this driver's qualification",
    "restricted": "Something on the record limits what this driver may do",
    "disqualified": "This driver may not drive",
}


class MvrReviewIn(BaseModel):
    finding: str = "qualified"
    note: str | None = None
    # What the medical certification block on a CDLIS record says. Asked here as well as on the
    # filing form, because a record that came back against an order is read HERE - the office never
    # touches the filing form for it, and a question only the filing form asks is a question nobody
    # ever answers for an ordered record.
    selfcert: str | None = None
    medcertstatus: str | None = None
    medcertexpires: date | None = None
    medvariancetype: str | None = None
    medvariance: str | None = None


@router.post("/drivers/{driverid}/mvrs/{mvrid}/reviewed")
def mark_mvr_reviewed(driverid: str, mvrid: str, body: MvrReviewIn, request: Request,
                      user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Record that somebody has read this driving record - the violations, suspensions, revocations
    and accidents on it. Reading it is what puts the annual review of it on the table; until then
    the record is on file and unread, which is not the same as reviewed."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    mvr = row(conn, """
        SELECT recordid, receivedon FROM drivermvrs
        WHERE recordid = :m AND accountid = :a AND driverid = :d
    """, m=mvrid, a=acct, d=driverid)
    if not mvr:
        raise HTTPException(404, "No such driving record")
    if not mvr["receivedon"]:
        raise HTTPException(409, "That record has not come back yet")
    finding = (getattr(body, "finding", None) or "qualified").strip()
    if finding not in MVR_FINDINGS:
        raise HTTPException(400, "Say what reading the record concluded")
    if finding == "restricted" and not (body.note or "").strip():
        raise HTTPException(400, "Say what the restriction is")
    if body.selfcert and body.selfcert not in SELF_CERT:
        raise HTTPException(400, "Unknown self-certification category")
    if body.medcertstatus and body.medcertstatus not in MED_CERT_STATUS:
        raise HTTPException(400, "Unknown medical certification status")
    if body.medvariancetype and body.medvariancetype not in MED_VARIANCE:
        raise HTTPException(400, "Unknown kind of medical variance")
    # COALESCE on each: a reviewer who says nothing about the medical block leaves what is already
    # there rather than wiping it. Somebody reading a record for its convictions should not be able
    # to silently erase the State's answer about medical qualification by not mentioning it.
    run(conn, """
        UPDATE drivermvrs SET reviewstate = 'reviewed', finding = :f, reviewedon = :now,
               reviewedby = :u, note = COALESCE(:n, note),
               selfcert = COALESCE(:sc, selfcert),
               medcertstatus = COALESCE(:ms, medcertstatus),
               medcertexpires = COALESCE(:mx, medcertexpires),
               medvariancetype = COALESCE(:mvt, medvariancetype),
               medvariance = COALESCE(:mv, medvariance)
        WHERE recordid = :m
    """, f=finding, now=utcnow(), u=user["recordid"], n=(body.note or "").strip() or None, m=mvrid,
        sc=(body.selfcert or None), ms=(body.medcertstatus or None), mx=body.medcertexpires,
        mvt=(body.medvariancetype or None),
        mv=(body.medvariance or "").strip()[:160] or None)
    log(conn, user, "reviewed", "drivermvr", driverid, {"mvrid": mvrid, "finding": finding},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class MvrOrderIn(BaseModel):
    licenseid: str
    note: str | None = None


EXAM_TYPES = {"preemployment", "biennial", "followup", "returntoduty"}
EXAM_RESULTS = {"meets", "meetsperiodic", "doesnotmeet", "temporary"}
EXAMINER_TYPES = {"MD", "DO", "PA", "ARNP"}
# 14-90.0041 asks for an examination at least every two years, so that is what "meets standards"
# buys where the examiner did not shorten it themselves.
TRANSIT_MEDICAL_YEARS = 2


@router.post("/drivers/{driverid}/transit-medicals")
async def file_transit_medical(
    driverid: str,
    request: Request,
    examtype: str = Form(...),
    examinedon: date = Form(...),
    result: str = Form(...),
    qualifiedthrough: date | None = Form(None),
    examinername: str | None = Form(None),
    examinerlicense: str | None = Form(None),
    examinerstate: str | None = Form(None),
    examinertype: str | None = Form(None),
    correctivelenses: bool = Form(False),
    hearingaid: bool = Form(False),
    otherrestriction: str | None = Form(None),
    tempreason: str | None = Form(None),
    followupon: date | None = Form(None),
    file: UploadFile | None = File(None),
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    """Record a bus transit medical examination - FDOT 725-030-11, F.A.C. 14-90.0041.

    What is stored is the certification: the occasion, the examiner, the determination and how long
    it stands. The health history and the examination findings on the form are not stored and have
    nowhere to go - the examiner keeps the complete examination, and the system keeps the
    certification. See migration 126."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    if examtype not in EXAM_TYPES:
        raise HTTPException(400, "Say which kind of examination this was")
    if result not in EXAM_RESULTS:
        raise HTTPException(400, "Say what the examiner determined")
    if examinertype and examinertype.upper() not in EXAMINER_TYPES:
        raise HTTPException(400, "Unknown kind of medical examiner")
    if result == "temporary" and not (tempreason or "").strip():
        raise HTTPException(400, "Say what the temporary disqualification is for")

    # How long it stands. An examiner who shortened it said so on the form, and that date is used as
    # written; the two years is only the default the rule gives where they did not.
    if result == "meetsperiodic" and not qualifiedthrough:
        raise HTTPException(400, "A periodic evaluation needs the date it is qualified through")
    if result in ("doesnotmeet", "temporary"):
        # Neither is qualified through anything - one has a follow-up date instead.
        qualifiedthrough = None
    elif not qualifiedthrough:
        qualifiedthrough = examinedon.replace(year=examinedon.year + TRANSIT_MEDICAL_YEARS)
    if qualifiedthrough and qualifiedthrough < examinedon:
        raise HTTPException(400, "It cannot be qualified through a date before the examination")

    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename,
                                  file.content_type, user["recordid"], origin=storage.OFFICE)

    recordid = newid()
    run(conn, """
        INSERT INTO transitmedicals (recordid, accountid, driverid, examtype, examinedon,
                                     examinername, examinerlicense, examinerstate, examinertype,
                                     result, qualifiedthrough, correctivelenses, hearingaid,
                                     otherrestriction, tempreason, followupon,
                                     documentid, createdby)
        VALUES (:id, :a, :d, :t, :on, :name, :lic, :st, :kind, :res, :through, :lens, :hear,
                :other, :why, :follow, :doc, :u)
    """, id=recordid, a=acct, d=driverid, t=examtype, on=examinedon,
        name=(examinername or None), lic=(examinerlicense or None),
        st=(examinerstate or None), kind=(examinertype or "").upper() or None,
        res=result, through=qualifiedthrough, lens=1 if correctivelenses else 0,
        hear=1 if hearingaid else 0, other=(otherrestriction or None),
        why=(tempreason or None), follow=followupon,
        doc=documentid, u=user["recordid"])
    _filed_here(conn, acct, driverid, "transitmedicals", recordid, user["recordid"])
    log(conn, user, "file", "transitmedical", driverid,
        {"result": result, "examtype": examtype}, ip=client_ip(request))
    saved(conn)
    return {"ok": True, "recordid": recordid}


@router.post("/drivers/{driverid}/mvrs/order")
def order_mvr(driverid: str, body: MvrOrderIn, request: Request,
              user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Send for a driving record on one licence. TripProof does not pull it - the office does, at
    the state - so this records which licence was asked about, by whom, and when."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    lic = row(conn, """
        SELECT recordid FROM driverlicenses WHERE recordid = :l AND accountid = :a AND driverid = :d
    """, l=body.licenseid, a=acct, d=driverid)
    if not lic:
        raise HTTPException(404, "That licence is not on this driver")
    waiting = _unfinished_mvr(conn, acct, body.licenseid)
    if waiting:
        raise HTTPException(409, _blocked_by(waiting))
    mvrid = newid()
    run(conn, """
        INSERT INTO drivermvrs (recordid, accountid, driverid, licenseid, orderedon, orderedby, note)
        VALUES (:id, :a, :d, :l, :now, :u, :n)
    """, id=mvrid, a=acct, d=driverid, l=body.licenseid, now=utcnow(), u=user["recordid"],
        n=(body.note or "").strip() or None)
    log(conn, user, "order", "drivermvr", driverid, {"licenseid": body.licenseid}, ip=client_ip(request))
    saved(conn)
    return {"ok": True, "recordid": mvrid}


@router.post("/drivers/{driverid}/mvrs/{mvrid}/cancel")
def cancel_mvr_order(driverid: str, mvrid: str, request: Request,
                     user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Withdraw a request that has not come back.

    The request is marked withdrawn rather than removed. Somebody asked a licensing authority a
    question on a date, usually for money, and that happened whether or not it should have. What
    changes is that the licence is no longer blocked: another request can be placed, or a record
    filed by hand.

    A request that has already been answered cannot be withdrawn - the answer is on file, and
    pretending it was never asked would leave a record attached to nothing."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    got = row(conn, """
        SELECT recordid, licenseid, receivedon, cancelledon FROM drivermvrs
        WHERE recordid = :m AND accountid = :a AND driverid = :d AND orderedon IS NOT NULL
    """, m=mvrid, a=acct, d=driverid)
    if not got:
        raise HTTPException(404, "There is no such request on this driver")
    if got["receivedon"]:
        raise HTTPException(409, "That request has already come back")
    if got["cancelledon"]:
        return {"ok": True, "recordid": mvrid}
    run(conn, """
        UPDATE drivermvrs SET cancelledon = :now, cancelledby = :u WHERE recordid = :m
    """, now=utcnow(), u=user["recordid"], m=mvrid)
    log(conn, user, "cancel", "drivermvr", driverid, {"licenseid": got["licenseid"]},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True, "recordid": mvrid}


@router.post("/drivers/{driverid}/mvrs")
async def file_mvr(
    driverid: str,
    request: Request,
    licenseid: str = Form(...),
    issuedon: date = Form(...),
    note: str | None = Form(None),
    # What reading it concluded, where whoever filed it has already read it. Optional: a record can
    # be filed now and read later, and saying nothing leaves it plainly unread rather than quietly
    # counting as fine.
    finding: str | None = Form(None),
    mvrid: str | None = Form(None),          # filling an order that was already placed
    # What a CDLIS record carries beyond the driving history. Optional on the form because not
    # every record is one - a non-CDL driver's MVR has none of this, and a State that does not
    # carry it says so with "notshown" rather than by leaving the question unanswered.
    selfcert: str | None = Form(None),       # NI | EI | NA | EA
    medcertstatus: str | None = Form(None),  # certified | notcertified | notshown
    medcertexpires: date | None = Form(None),
    medvariancetype: str | None = Form(None),   # spe | exemption
    medvariance: str | None = Form(None),       # its reference and any limitation on it
    file: UploadFile | None = File(None),
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    """File a driving record against the licence it was pulled on, with the record itself. It also
    becomes a credential, so the trip checks and the annual review read it exactly as they always
    have - and the annual review has something to read."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    if file is None or not file.filename:
        raise HTTPException(400, "Attach the driving record")
    lic = row(conn, """
        SELECT recordid FROM driverlicenses WHERE recordid = :l AND accountid = :a AND driverid = :d
    """, l=licenseid, a=acct, d=driverid)
    if not lic:
        raise HTTPException(404, "That licence is not on this driver")
    # An upload fills an order only when it SAYS which order - the record coming back names the
    # request it answers. Matching `:m IS NULL` to any outstanding request meant a fresh upload
    # silently closed one, so a record pulled for another reason was filed as the answer to a
    # question nobody had asked it.
    outstanding = row(conn, """
        SELECT recordid FROM drivermvrs WHERE accountid = :a AND driverid = :d AND licenseid = :l
          AND receivedon IS NULL AND cancelledon IS NULL AND recordid = :m LIMIT 1
    """, a=acct, d=driverid, l=licenseid, m=mvrid) if mvrid else None
    if mvrid and not outstanding:
        raise HTTPException(404, "That request is not outstanding on this license")
    if not outstanding:
        # Not filling an order: this would be a new record, and nothing new can be filed on a
        # licence with a request still out - the answer on its way would have nothing to attach to.
        waiting = _unfinished_mvr(conn, acct, licenseid)
        if waiting:
            raise HTTPException(409, _blocked_by(waiting))

    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename,
                                  file.content_type, user["recordid"], origin=storage.OFFICE)

    credentialid = newid()
    run(conn, """
        INSERT INTO credentials (recordid, accountid, credentialtypeid, subject, subjectid, documentid,
                                 issuedon, issuer, notes, enteredby)
        VALUES (:id, :a, :t, 'driver', :d, :doc, :on, :by, :n, :u)
    """, id=credentialid, a=acct, t=_mvr_type(conn), d=driverid, doc=documentid, on=issuedon,
        by=user["name"][:128], n=(note or None), u=user["recordid"])

    now = utcnow()
    # Filing a record is not reading it. Both branches used to write reviewstate = 'reviewed'
    # outright, so a record that nobody had looked at counted as reviewed and carried no finding -
    # which is the one state this whole thing exists to make visible. It is read only if whoever
    # filed it says what it concluded.
    if finding is not None and finding not in MVR_FINDINGS:
        raise HTTPException(400, "Say what reading the record concluded")
    if selfcert and selfcert not in SELF_CERT:
        raise HTTPException(400, "Unknown self-certification category")
    if medcertstatus and medcertstatus not in MED_CERT_STATUS:
        raise HTTPException(400, "Unknown medical certification status")
    if medvariancetype and medvariancetype not in MED_VARIANCE:
        raise HTTPException(400, "Unknown kind of medical variance")
    if finding == "restricted" and not (note or "").strip():
        raise HTTPException(400, "Say what the restriction is")
    seen = "reviewed" if finding else "pending"
    read_on, read_by = (now, user["recordid"]) if finding else (None, None)

    if outstanding:
        mvrid_ = outstanding["recordid"]
        run(conn, """
            UPDATE drivermvrs SET issuedon = :on, receivedon = :now, receivedby = :u, documentid = :doc,
                   credentialid = :c, note = COALESCE(:n, note),
                   reviewstate = :seen, finding = :f, reviewedon = :ron, reviewedby = :rby,
                   selfcert = :sc, medcertstatus = :ms, medcertexpires = :mx,
                   medvariancetype = :mvt, medvariance = :mv
            WHERE recordid = :id
        """, on=issuedon, now=now, u=user["recordid"], doc=documentid, c=credentialid,
            n=(note or None), seen=seen, f=finding, ron=read_on, rby=read_by, id=mvrid_,
            sc=(selfcert or None), ms=(medcertstatus or None), mx=medcertexpires,
            mvt=(medvariancetype or None), mv=(medvariance or "").strip()[:160] or None)
    else:
        mvrid_ = newid()
        run(conn, """
            INSERT INTO drivermvrs (recordid, accountid, driverid, licenseid, credentialid, issuedon,
                                    receivedon, receivedby, documentid, note, reviewstate, finding,
                                    reviewedon, reviewedby, selfcert, medcertstatus, medcertexpires,
                                    medvariancetype, medvariance)
            VALUES (:id, :a, :d, :l, :c, :on, :now, :u, :doc, :n, :seen, :f, :ron, :rby,
                    :sc, :ms, :mx, :mvt, :mv)
        """, id=mvrid_, a=acct, d=driverid, l=licenseid, c=credentialid, on=issuedon,
            now=now, u=user["recordid"], doc=documentid, n=(note or None), seen=seen, f=finding,
            ron=read_on, rby=read_by, sc=(selfcert or None), ms=(medcertstatus or None),
            mx=medcertexpires, mvt=(medvariancetype or None),
            mv=(medvariance or "").strip()[:160] or None)
    # The record has arrived and is waiting to be read - which is what `reviewstate` says, and is
    # the whole of what arriving means.
    #
    # It deliberately does NOT open an annual review. 49 CFR 391.25 asks for one determination about
    # one driver at least once every 12 months, on its own schedule; a record ordered in between -
    # to check on somebody, or because a second state was outstanding - is evidence, not an occasion
    # for a second annual. Reading it is its own job, and if what it says disqualifies the driver
    # that takes effect at once rather than waiting for the annual to come round.
    # A driving record is made by a licensing authority, so it arrives from outside whether it
    # answers an order or was pulled by hand, and it is unread until somebody here reads it.
    if outstanding:
        _came_in(conn, acct, driverid, "MVR_PREEMPLOYMENT", "A driving record",
                 "drivermvrs", mvrid_)
    else:
        _filed_here(conn, acct, driverid, "drivermvrs", mvrid_, user["recordid"])
    log(conn, user, "file", "drivermvr", driverid,
        {"licenseid": licenseid, "issuedon": str(issuedon)}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "evaluation": evaluation}


@router.delete("/drivers/{driverid}/mvrs/{mvrid}")
def cancel_mvr_order(driverid: str, mvrid: str, request: Request,
                     user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Take back an order that was placed by mistake. A record already filed is not removed here -
    what is on file was on file."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    held = row(conn, """
        SELECT recordid, receivedon FROM drivermvrs WHERE recordid = :m AND accountid = :a AND driverid = :d
    """, m=mvrid, a=acct, d=driverid)
    if not held:
        raise HTTPException(404, "No such order")
    if held["receivedon"]:
        raise HTTPException(409, "That record is on file")
    run(conn, "DELETE FROM drivermvrs WHERE recordid = :m", m=mvrid)
    log(conn, user, "cancel", "drivermvr", driverid, {"mvrid": mvrid}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


def _open_review(conn: Connection, accountid: str, driverid: str, reviewid: str) -> dict:
    """The open review a completion is finishing. A review is opened by its driving record arriving,
    so completing one means finishing work already on the books rather than inventing it here."""
    review = row(conn, """
        SELECT r.recordid, r.licenseid, r.mvrid, r.mvron, r.finding, r.snapshot, m.reviewstate
        FROM annualreviews r LEFT JOIN drivermvrs m ON m.recordid = r.mvrid
        WHERE r.recordid = :r AND r.accountid = :a AND r.driverid = :d
    """, r=reviewid, a=accountid, d=driverid)
    if not review:
        raise HTTPException(404, "No such review")
    if review["finding"]:
        raise HTTPException(409, "That review is already complete")
    return review


def _review_credential(conn: Connection, accountid: str, driverid: str, user: dict, on: date,
                       finding: str, documentid: str | None) -> str:
    """The completed review, as the credential every check reads."""
    ctype = row(conn, "SELECT recordid FROM credentialtypes WHERE code = 'ANNUAL_REVIEW'")
    credentialid = newid()
    run(conn, """
        INSERT INTO credentials (recordid, accountid, credentialtypeid, subject, subjectid, documentid,
                                 issuedon, issuer, notes, enteredby)
        VALUES (:id, :a, :t, 'driver', :d, :doc, :on, :by, :notes, :u)
    """, id=credentialid, a=accountid, t=ctype["recordid"], d=driverid, doc=documentid, on=on,
        by=user["name"][:128], notes=annualreview.FINDINGS[finding][:512], u=user["recordid"])
    return credentialid


@router.get("/drivers/{driverid}/annual-reviews")
def driver_annual_reviews(driverid: str, user: dict = Depends(current_user),
                          conn: Connection = Depends(get_conn)):
    """Every review on file, and what a new one would be filled in with: the driver and the licence
    as they read now, and the date of the driving record waiting to be reviewed."""
    acct = user["accountid"]
    driver = row(conn, """
        SELECT recordid, firstname, lastname, dob, licensenumber, licensestate, licenseclass, operatescmv
        FROM drivers WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=driverid, a=acct)
    if not driver:
        raise HTTPException(404, "No such driver")
    mvr = row(conn, """
        SELECT c.issuedon FROM credentials c JOIN credentialtypes t ON t.recordid = c.credentialtypeid
        WHERE c.accountid = :a AND c.subject = 'driver' AND c.subjectid = :d AND c.deleted IS NULL
          AND t.code = 'MVR' ORDER BY c.issuedon DESC LIMIT 1
    """, a=acct, d=driverid)
    reviews = annualreview.listing(conn, acct, driverid)
    owed = annualreview.due(conn, acct, driverid)
    # Reviews belong to the licence their record was pulled on, so they are read that way: every
    # licence the driver holds, with the reviews opened against it.
    licences = _licences(conn, acct, driverid)
    for lic in licences:
        # The current review only - the one belonging to the record the licence stands on.
        lic["reviews"] = [r for r in reviews if r["licenseid"] == lic["recordid"]][:1]
    return {"due": owed,
            "driver": annualreview.snapshot(conn, acct, driver),
            "mvron": mvr["issuedon"] if mvr else None,
            # Whether the review can be completed at all, and from which authorities a record is
            # still missing. Sent with the reviews so the screen that offers the determination is
            # reading the same answer the server will enforce.
            "coverage": annualreview.readiness(conn, acct, driverid),
            "findings": annualreview.FINDINGS,
            "needsreason": list(annualreview.NEEDS_REASON),
            "goodfaith": (annualreview.GOOD_FAITH_CMV if driver["operatescmv"]
                          else annualreview.GOOD_FAITH_OTHER),
            "licenses": licences,
            "reviews": reviews}


@router.post("/drivers/{driverid}/annual-review/start")
def start_annual_review(driverid: str, request: Request, user: dict = Depends(editor),
                        conn: Connection = Depends(get_conn)):
    """Open this driver's annual review, gathering the records it will be performed against.

    Nothing opens one on its own any more. 49 CFR 391.25 is a deadline the office works to, not
    something a record arriving sets off - so the review is started deliberately, once, and every
    driving record received in the period it covers is attached to it."""
    acct = user["accountid"]
    driver = row(conn, """
        SELECT recordid, firstname, lastname, dob, licensenumber, licensestate, licenseclass, operatescmv
        FROM drivers WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=driverid, a=acct)
    if not driver:
        raise HTTPException(404, "No such driver")
    reviewid = annualreview.start(conn, acct, driver)
    log(conn, user, "open", "annualreview", driverid, {"reviewid": reviewid}, ip=client_ip(request))
    saved(conn)
    return {"recordid": reviewid}


@router.post("/drivers/{driverid}/annual-review")
async def file_annual_review(
    driverid: str,
    request: Request,
    reviewid: str = Form(...),
    finding: str = Form("qualified"),
    note: str | None = Form(None),
    signatureid: str = Form(...),
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    """The yearly review of a driver's driving record, performed here and signed.

    49 CFR 391.25(c)(2) asks for the name of the person who performed the review, so the form is
    signed rather than merely dated - with that person's own signature, created once behind their
    date of birth and Social Security number and proved again whenever they sign."""
    acct = user["accountid"]
    driver = row(conn, """
        SELECT recordid, firstname, lastname, dob, licensenumber, licensestate, licenseclass, operatescmv
        FROM drivers WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=driverid, a=acct)
    if not driver:
        raise HTTPException(404, "No such driver")
    if finding not in annualreview.FINDINGS:
        raise HTTPException(400, "Say what the review found")
    # A finding that needs explaining has to carry the explanation. "Corrective action required"
    # with nothing said is the same as saying nothing.
    if finding in annualreview.NEEDS_REASON and not (note or "").strip():
        raise HTTPException(400, "Say what was found and what is being done about it")
    # 49 CFR 391.25(a) asks for the record of each State the driver was licensed in. A
    # determination signed while an authority is still silent is a determination made without the
    # evidence, so it is refused here and not merely discouraged on the screen - the screen is
    # not the thing that has to be right.
    ready = annualreview.readiness(conn, acct, driverid)
    if not ready.get("complete"):
        missing = ", ".join(ready.get("missing") or []) or "another licensing authority"
        raise HTTPException(
            409, f"No current driving record on file from {missing}. "
                 "The review cannot be completed until every licensing authority has answered.")
    review = _open_review(conn, acct, driverid, reviewid)
    # The signature is the one they proved was theirs a moment ago, not a name typed into a box.
    sig = signatures.current(conn, acct, "user", user["recordid"])
    if not sig or sig["recordid"] != signatureid:
        raise HTTPException(409, "Sign the review with your own signature")
    # The signature date is the day it was signed, stamped by the signing - not a date chosen on a
    # form before anybody had put their name to it.
    reviewedon = localnow(user["timezone"]).date()

    annualreview.complete(
        conn, acct, review, driver, reviewedon=reviewedon, finding=finding, note=note,
        reviewer=user["name"], signatureid=sig["recordid"], method="form",
        enteredby=user["recordid"], ip=client_ip(request),
        useragent=request.headers.get("user-agent"))

    # The review is also a credential: it is what the rule looks at, and it goes stale in a year.
    credentialid = _review_credential(conn, acct, driverid, user, reviewedon, finding, None)
    run(conn, "UPDATE annualreviews SET credentialid = :c WHERE recordid = :id",
        c=credentialid, id=reviewid)
    log(conn, user, "review", "driver", driverid,
        {"reviewedon": str(reviewedon), "finding": finding, "reviewid": reviewid},
        ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "recordid": reviewid, "evaluation": evaluation}


@router.post("/drivers/{driverid}/annual-review/copy")
async def file_annual_review_copy(
    driverid: str,
    request: Request,
    reviewid: str = Form(...),
    finding: str = Form(...),
    completedon: date = Form(...),
    reviewer: str = Form(...),
    note: str | None = Form(None),
    file: UploadFile = File(...),
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    """A review performed on paper somewhere else, filed against the record it was made on.

    The scan is not the result: nothing here can read what a form says, and a file that cannot say
    whether the driver was found qualified cannot answer the question a review exists to answer. So
    the finding, the date it was completed and who made it are asked for alongside the copy."""
    acct = user["accountid"]
    driver = row(conn, """
        SELECT recordid, firstname, lastname, dob, licensenumber, licensestate, licenseclass, operatescmv
        FROM drivers WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=driverid, a=acct)
    if not driver:
        raise HTTPException(404, "No such driver")
    if finding not in annualreview.FINDINGS:
        raise HTTPException(400, "Say whether the review found this driver qualified")
    if not (reviewer or "").strip():
        raise HTTPException(400, "Name whoever performed the review")
    review = _open_review(conn, acct, driverid, reviewid)

    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "That file is larger than 20 MB")
    documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                              user["recordid"], origin=storage.OFFICE)

    annualreview.complete(
        conn, acct, review, driver, reviewedon=completedon, finding=finding, note=note,
        reviewer=reviewer.strip(), signatureid=None, method="upload", documentid=documentid,
        filedon=completedon, enteredby=user["recordid"], ip=client_ip(request),
        useragent=request.headers.get("user-agent"))
    credentialid = _review_credential(conn, acct, driverid, user, completedon, finding, documentid)
    run(conn, "UPDATE annualreviews SET credentialid = :c WHERE recordid = :id",
        c=credentialid, id=reviewid)
    log(conn, user, "review-filed", "driver", driverid,
        {"reviewid": reviewid, "finding": finding, "completedon": str(completedon)}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "recordid": reviewid, "evaluation": evaluation}


@router.get("/drivers/{driverid}/files")
def driver_files(driverid: str, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Everything on file for this driver, in sections: what they uploaded with their application,
    what the office has filed against them since, and what they signed.

    A signed document is not a file in the store - it is rebuilt from the record when it is read -
    so it is listed apart, and opened its own way."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    uploaded, filed, seen = [], [], set()

    app_ = row(conn, """
        SELECT data FROM driverapplications WHERE driverid = :d AND accountid = :a
        ORDER BY startedon DESC LIMIT 1
    """, d=driverid, a=acct)
    uploads = (json.loads(app_["data"] or "{}").get("uploads") or {}) if app_ else {}
    for kind, up in uploads.items():
        doc = row(conn, """
            SELECT recordid, filename, mimetype, bytes, added FROM documents
            WHERE recordid = :id AND accountid = :a AND deleted IS NULL
        """, id=up.get("documentid"), a=acct) if up.get("documentid") else None
        if doc and doc["recordid"] not in seen:
            seen.add(doc["recordid"])
            uploaded.append({**doc, "kind": "file", "origin": "driver",
                             "category": APPLICATION_CATEGORY.get(kind, "Anything else"),
                             "what": applicationview.UPLOAD_LABELS.get(kind, kind.replace("_", " ").capitalize())})

    for c in rows(conn, """
        SELECT d.recordid, d.filename, d.mimetype, d.bytes, d.added, d.origin,
               t.name AS what, t.category, t.code AS typecode, c.recordid AS credentialid
        FROM credentials c
        JOIN credentialtypes t ON t.recordid = c.credentialtypeid
        JOIN documents d ON d.recordid = c.documentid
        WHERE c.accountid = :a AND c.subject = 'driver' AND c.subjectid = :d
          AND c.deleted IS NULL AND d.deleted IS NULL
        ORDER BY c.issuedon DESC
    """, a=acct, d=driverid):
        if c["recordid"] not in seen:
            seen.add(c["recordid"])
            filed.append({**c, "kind": "file",
                          "category": _category(c["category"], c["typecode"])})

    # Drug and alcohol. These were in the store, attached to the right records, and reachable
    # only three screens deep - D&A Testing History, View on a positive, then View inside the
    # prohibition. Nobody looks there for a document; they look in the file. Tim had fourteen of
    # them and his file listed none.
    #
    # It matters beyond being hard to find: 49 CFR 382.401 asks the employer to KEEP these, and
    # the downloadable driver file is built from this same list - so the record handed to an
    # auditor was missing every lab report and every SAP determination the office had uploaded.
    da = []
    for t in rows(conn, """
        SELECT d.recordid, d.filename, d.mimetype, d.bytes, d.added, d.origin,
               t.reason, t.result, t.collectedon
        FROM drugtests t JOIN documents d ON d.recordid = t.documentid AND d.deleted IS NULL
        WHERE t.accountid = :a AND t.driverid = :d AND t.withdrawn IS NULL
        ORDER BY t.collectedon DESC
    """, a=acct, d=driverid):
        if t["recordid"] in seen:
            continue
        seen.add(t["recordid"])
        # Named by what it is rather than by what the lab called the PDF: an auditor reading a
        # list of eight files wants to know which is the positive one.
        da.append({**t, "kind": "file", "category": "Drug and alcohol testing",
                   "what": f'{eligibility.REASONS.get(t["reason"], t["reason"])} test'
                           f' {t["collectedon"]:%m/%d/%Y}'
                           f' - {eligibility.RESULTS.get(t["result"], t["result"])}'})

    for which, label in (("documentid", "SAP determination"),
                         ("sapinfodocumentid",
                          "List of substance abuse professionals given to the driver")):
        for b in rows(conn, f"""
            SELECT d.recordid, d.filename, d.mimetype, d.bytes, d.added, d.origin, p.startedon
            FROM driverprohibitions p
            JOIN documents d ON d.recordid = p.{which} AND d.deleted IS NULL
            WHERE p.accountid = :a AND p.driverid = :d AND p.withdrawn IS NULL
            ORDER BY p.startedon DESC
        """, a=acct, d=driverid):
            if b["recordid"] in seen:
                continue
            seen.add(b["recordid"])
            da.append({**b, "kind": "file", "category": "Drug and alcohol testing",
                       "what": f'{label} - violation of {b["startedon"]:%m/%d/%Y}'})

    signed = [{"kind": "signed", "doctype": s["doctype"], "what": s["title"],
               "added": s["signedon"], "filename": s["typedname"], "bytes": None,
               "category": "Signed documents", "origin": who}
              for who, lot in (("driver", applicationview.signed_list(conn, acct, driverid)),
                               ("office", _reviews_signed(conn, acct, driverid)))
              for s in lot]

    # Everything else that holds a document. The folder used to show credentials and nothing
    # else, so the licence copies the office scanned, the driving records, the annual reviews,
    # the road test certificate, the transit medical and the previous employer's reply were all
    # in the store, attached to the right records, and absent from the one screen called Files.
    other = []
    for sql, what, cat in (
        ("""SELECT d.recordid, d.filename, d.mimetype, d.bytes, d.added, d.origin,
                   CONCAT(l.state, ' ', l.number) AS detail
            FROM driverlicenses l JOIN documents d ON d.recordid = l.copydocumentid
            WHERE l.accountid = :a AND l.driverid = :d AND d.deleted IS NULL""",
         "Copy of the driver's license", "Driver's license"),
        ("""SELECT d.recordid, d.filename, d.mimetype, d.bytes, d.added, d.origin,
                   DATE_FORMAT(m.issuedon, '%m/%d/%Y') AS detail
            FROM drivermvrs m JOIN documents d ON d.recordid = m.documentid
            WHERE m.accountid = :a AND m.driverid = :d AND d.deleted IS NULL""",
         "Motor vehicle record", "Driving record"),
        ("""SELECT d.recordid, d.filename, d.mimetype, d.bytes, d.added, d.origin,
                   DATE_FORMAT(r.reviewedon, '%m/%d/%Y') AS detail
            FROM annualreviews r JOIN documents d ON d.recordid = r.documentid
            WHERE r.accountid = :a AND r.driverid = :d AND d.deleted IS NULL""",
         "Annual review of the driving record", "Driving record"),
        ("""SELECT d.recordid, d.filename, d.mimetype, d.bytes, d.added, d.origin,
                   DATE_FORMAT(t.testedon, '%m/%d/%Y') AS detail
            FROM roadtests t JOIN documents d ON d.recordid = t.documentid
            WHERE t.accountid = :a AND t.driverid = :d AND d.deleted IS NULL""",
         "Road test certificate", "Road test"),
        ("""SELECT d.recordid, d.filename, d.mimetype, d.bytes, d.added, d.origin,
                   DATE_FORMAT(m.examinedon, '%m/%d/%Y') AS detail
            FROM transitmedicals m JOIN documents d ON d.recordid = m.documentid
            WHERE m.accountid = :a AND m.driverid = :d AND d.deleted IS NULL""",
         "Transit medical examination", "Medical"),
        ("""SELECT d.recordid, d.filename, d.mimetype, d.bytes, d.added, d.origin,
                   COALESCE(NULLIF(:psp, ''), r.code) AS detail, r.code AS reportcode
            FROM driverreports r JOIN documents d ON d.recordid = r.documentid
            WHERE r.accountid = :a AND r.driverid = :d AND d.deleted IS NULL""",
         None, "Screening"),
        ("""SELECT d.recordid, d.filename, d.mimetype, d.bytes, d.added, d.origin,
                   i.employer AS detail
            FROM employerinquiries i JOIN documents d ON d.recordid = i.documentid
            WHERE i.accountid = :a AND i.driverid = :d AND d.deleted IS NULL""",
         "Safety performance history reply", "Previous employer"),
    ):
        for x in rows(conn, sql, a=acct, d=driverid, psp=""):
            if x["recordid"] in seen:
                continue
            seen.add(x["recordid"])
            # A report is named by what it is. REPORTS already holds those words, and
            # printing CLEARINGHOUSE_PREEMP at somebody is printing our column at them.
            said = what or REPORTS.get(x.get("reportcode"), "Report")
            tail = x.get("detail") if what else None
            other.append({**x, "kind": "file", "category": cat,
                          "what": f"{said} - {tail}" if tail else said})

    everything = uploaded + filed + da + signed + other
    return {"sections": [
        {"name": name,
         "files": sorted((f for f in everything if f.get("category") == name),
                         key=lambda f: str(f["added"]), reverse=True)}
        for name in FILE_CATEGORIES
        if any(f.get("category") == name for f in everything)]}


# Which files the office may take back: the ones the office put there, and nothing else.
#
# A driver's own submission, what a service returned, what a previous employer sent - those are
# somebody else's record of what they did, and a carrier that can quietly remove them can quietly
# remove the inconvenient ones. An unknown origin is NOT the office: these rows predate the stamp
# and "nobody can show who filed this" must never read as "so you may delete it".
WITHDRAWABLE = "office"

# What a file IS, which is how somebody looks for one.
#
# The folder used to be grouped by where each document came from - uploaded with the
# application, filed by the office, signed by the driver. That is the right question when you
# are asking whether a file may be withdrawn and the wrong one when you are asking whether the
# medical certificate is on hand: it puts a licence copy the driver sent and a licence copy the
# office scanned in two different places, pages apart.
#
# So the grouping is the category and the origin moved onto the row, where it decides the
# Withdraw button and says in words who sent it.
#
# Drug and alcohol keeps a heading of its own, as it did before: 49 CFR 40.321 restricts who
# that information may be released to, and a section that names itself is one somebody can
# think twice about before forwarding.
# Taken from every driver rule that can take a file, not from the credential types alone -
# which is what the first cut did, so the licence, the driving record, the road test, the
# transit medical and the previous employer's reply had nowhere to be grouped under.
FILE_CATEGORIES = [
    "Driver's license",            # the licence, its copies, any action against it
    "Medical",                     # the DOT card, the FDOT transit examination, an SPE
    "Driving record",              # MVRs and the annual review of them
    "Screening",                   # background, exclusion lists, Clearinghouse, fingerprints
    "Road test",
    "Training",
    "Testing",                     # a non-DOT screen, which is not Part 382 testing
    "Drug and alcohol testing",    # DOT tests and the SAP paperwork - see 49 CFR 40.321
    "Previous employer",
    "Signed documents",
    "Anything else",
]

# Where a credential type goes when its own `category` is too coarse. A medical card and an
# abuse registry check are both "licensing" and "screening" to the catalogue, and neither is
# what somebody opening the folder is looking under.
CATEGORY_BY_CODE = {
    "DOT_MEDICAL_CARD": "Medical",
    "SPE_CERTIFICATE": "Medical",
    "FL_LICENSE_ACTION": "Driver's license",
    "MISCELLANEOUS": "Anything else",
    # Retired credential types - driving records are their own records now - but credentials
    # filed against them before that are still in the folder, and their old category said
    # `screening`, which put a driving record among the background checks.
    "MVR": "Driving record",
    "ANNUAL_REVIEW": "Driving record",
}

# The five things an applicant can attach, by what they are rather than by the step they were
# attached at.
APPLICATION_CATEGORY = {
    "license_front": "Driver's license", "license_back": "Driver's license",
    "license_action": "Driver's license", "medical_certificate": "Medical",
    "i9_document": "Anything else",
}


def _category(name: str | None, code: str | None = None) -> str:
    """Where a document belongs in the folder: its type's own word for it, unless the type is
    one of the handful the catalogue files too coarsely."""
    if code and code in CATEGORY_BY_CODE:
        return CATEGORY_BY_CODE[code]
    pretty = (name or "").strip().capitalize()
    return pretty if pretty in FILE_CATEGORIES else "Anything else"

ORIGIN_SAYS = {
    "driver": "The driver sent this in. It is their own submission and the office cannot "
              "withdraw it.",
    "service": "This came back from a service that was asked for it. The office cannot withdraw "
               "what it did not file.",
    "thirdparty": "This came from outside - a previous employer, or an examiner. The office "
                  "cannot withdraw somebody else's record.",
    None: "There is no record of who filed this, so it cannot be withdrawn from here.",
}


@router.get("/drivers/{driverid}/files/kinds")
def file_kinds(driverid: str, user: dict = Depends(current_user),
               conn: Connection = Depends(get_conn)):
    """What an uploaded file can BE, and what each kind needs asked alongside it.

    A file dropped into a driver's folder is not evidence of anything until somebody says what
    it is. A medical certificate answers 391.43 and runs out; a training record answers its own
    requirement and runs out on its own clock; a scan of something nobody has to keep is just a
    scan. So the upload asks which, and the fields follow from the answer rather than from a
    form that asks everybody for everything."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    kinds = []
    for t in rows(conn, """
        SELECT recordid, code, name, category, maxagedays, defaultvaliddays
        FROM credentialtypes
        WHERE subject = 'driver' AND active = 1 AND (accountid IS NULL OR accountid = :a)
        ORDER BY (code = 'MISCELLANEOUS'), COALESCE(category, 'zz'), name
    """, a=acct):
        life = t["maxagedays"] or t["defaultvaliddays"]
        kinds.append({
            "kind": "credential", "code": t["code"], "typeid": t["recordid"], "name": t["name"],
            "group": _category(t["category"], t["code"]),
            # Said on the form, because somebody typing an issue date should know whether the
            # expiry is being worked out for them or left blank on purpose.
            "life": life,
            "hint": (f"Leave the expiry blank and it is taken as {life} days from the issue date."
                     if life else "This kind does not run out unless the document says so."),
        })
    # The rest of what a driver's folder can hold. Every one of these takes a file, and none of
    # them is a credential - so offering only the credential types, as the first cut did, left
    # the licence, the driving record, the road test and the transit medical with no way in from
    # here at all.
    #
    # They are not rebuilt here. Each already has a screen that asks what it needs - which
    # licence a driving record was pulled on, what the examiner found, whether the driver was
    # certified - and a second form asking the same questions is a second form to get wrong. So
    # the picker names them and sends you to the one that exists.
    kinds += [
        {"kind": "licence", "code": "LICENCE", "name": "Driver's license",
         "group": "Driver's license",
         "hint": "The licence itself and a copy of each side, so the class and expiry are "
                 "checked against the work this driver is assigned."},
        {"kind": "requirement", "code": "MVR_PREEMPLOYMENT", "name": "Motor vehicle record",
         "group": "Driving record", "goto": "requirements",
         "hint": "Recorded against the licence it was pulled on, with the date it was issued."},
        {"kind": "requirement", "code": "MVR_ANNUAL",
         "name": "Annual review of the driving record", "group": "Driving record",
         "goto": "requirements",
         "hint": "49 CFR 391.25. The review is a finding somebody makes, not a file - the copy "
                 "is filed with it."},
        {"kind": "requirement", "code": "ROAD_TEST", "name": "Road test certificate",
         "group": "Road test", "goto": "requirements",
         "hint": "49 CFR 391.31. Who examined the driver and what they found."},
        {"kind": "requirement", "code": "FL_TRANSIT_MEDICAL",
         "name": "Transit medical examination", "group": "Medical", "goto": "requirements",
         "hint": "FDOT 725-030-11. The examiner's determination is the answer; the form is "
                 "filed with it."},
        {"kind": "requirement", "code": "SAFETY_PERFORMANCE_HISTORY",
         "name": "Previous employer's reply", "group": "Previous employer",
         "goto": "requirements",
         "hint": "49 CFR 391.23. Filed against the employer it came from."},
        {"kind": "test", "code": "DRUGTEST", "name": "Drug or alcohol test",
         "group": "Drug and alcohol testing", "goto": "testing",
         "hint": "The result is what matters and it has consequences, so it is recorded with "
                 "the lab report rather than as one."},
    ]
    # Same order as the folder, so what you pick here and where it lands read as one list
    # rather than two that happen to share words.
    kinds.sort(key=lambda k: (FILE_CATEGORIES.index(k["group"])
                              if k["group"] in FILE_CATEGORIES else len(FILE_CATEGORIES),
                              k["kind"] != "licence", k["name"]))
    return {"kinds": kinds}


class WithdrawFileIn(BaseModel):
    reason: str


@router.post("/drivers/{driverid}/files/{documentid}/withdraw")
def withdraw_file(driverid: str, documentid: str, body: WithdrawFileIn, request: Request,
                  user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Take back a file the office filed against the wrong driver, and what it was filed as.

    Only the office's own uploads. Everything else in the folder belongs to somebody else - the
    driver who sent it, the service that returned it, the previous employer who answered - and
    is refused here as well as hidden on the screen, so posting straight at the endpoint does
    not get round it."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    why = (body.reason or "").strip()
    if len(why) < 3:
        raise HTTPException(400, "Say why this file is being withdrawn")
    doc = row(conn, """
        SELECT recordid, filename, origin FROM documents
        WHERE recordid = :i AND accountid = :a AND deleted IS NULL
    """, i=documentid, a=acct)
    if not doc:
        raise HTTPException(404, "No such file")
    if doc["origin"] != WITHDRAWABLE:
        raise HTTPException(409, ORIGIN_SAYS.get(doc["origin"], ORIGIN_SAYS[None]))

    undone = []
    # What the file was filed AS goes with it. A medical certificate withdrawn while the
    # credential it created stays behind would leave the requirement reading satisfied against
    # a document that is no longer there.
    for c in rows(conn, """
        SELECT c.recordid, t.name FROM credentials c
        JOIN credentialtypes t ON t.recordid = c.credentialtypeid
        WHERE c.accountid = :a AND c.subject = 'driver' AND c.subjectid = :d
          AND c.documentid = :i AND c.deleted IS NULL
    """, a=acct, d=driverid, i=documentid):
        run(conn, "UPDATE credentials SET deleted = :now WHERE recordid = :r",
            r=c["recordid"], now=utcnow())
        undone.append(f'{c["name"]} is no longer on file, so the requirement it answered is '
                      f'outstanding again')
    n_lic = run(conn, """
        UPDATE driverlicenses SET copydocumentid = NULL
        WHERE accountid = :a AND driverid = :d AND copydocumentid = :i
    """, a=acct, d=driverid, i=documentid).rowcount
    if n_lic:
        undone.append("The licence it was filed as a copy of no longer has one")

    run(conn, "UPDATE documents SET deleted = :now WHERE recordid = :i AND accountid = :a",
        i=documentid, a=acct, now=utcnow())
    log(conn, user, "file-withdrawn", "driver", driverid,
        {"documentid": documentid, "filename": doc["filename"], "reason": why, "undone": undone},
        ip=client_ip(request))
    _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "undone": undone}


def _reviews_signed(conn: Connection, accountid: str, driverid: str) -> list[dict]:
    """Annual reviews read as signed documents: one per review, each its own sheet, because a
    review is made every year and the one made this year does not replace last year's."""
    return [{"doctype": f"ANNUAL_REVIEW:{r['recordid']}",
             "title": f"{annualreview.TITLE} - {r['reviewedon']:%Y}",
             "signedon": r["createdon"], "typedname": r["typedname"] or r["reviewer"],
             "ip": None, "recordid": r["recordid"]}
            for r in annualreview.listing(conn, accountid, driverid)]


class SignRequestIn(BaseModel):
    doctype: str


@router.post("/drivers/{driverid}/signing-requests")
def ask_for_a_signature(driverid: str, body: SignRequestIn, request: Request,
                        tasks: BackgroundTasks, user: dict = Depends(editor),
                        conn: Connection = Depends(get_conn)):
    """Ask this driver to sign one document, and send them the link. The link is answered here too,
    so the office can read it out to somebody who has no email."""
    acct = user["accountid"]
    driver = row(conn, """
        SELECT recordid, firstname, lastname, email FROM drivers
        WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=driverid, a=acct)
    if not driver:
        raise HTTPException(404, "No such driver")
    made = signing.create(conn, acct, driverid, body.doctype, user["recordid"])
    company = row(conn, "SELECT name FROM accounts WHERE recordid = :a", a=acct)["name"]
    if driver["email"]:
        run(conn, "UPDATE signingrequests SET sentto = :to, senton = :now WHERE recordid = :id",
            to=driver["email"], now=utcnow(), id=made["recordid"])
        subject, html, text = emails.signature_requested(
            name=f'{driver["firstname"]} {driver["lastname"]}'.strip(), accountname=company,
            document=signing.SIGNABLE[body.doctype], link=made["link"], days=made["days"])
        tasks.add_task(mailer.send, driver["email"], subject, html, text)
    log(conn, user, "signature-requested", "driver", driverid, {"doctype": body.doctype},
        ip=client_ip(request))
    events.record(conn, acct, "driver", driverid, "signature-requested", body.doctype)
    saved(conn)
    return {**made, "sentto": driver["email"]}


class UploadRequestIn(BaseModel):
    code: str


# ------------------------------------------------------------------------------------------------
# Previous employer safety performance history - 49 CFR 391.23(d), (e), (i)
# ------------------------------------------------------------------------------------------------

@router.get("/drivers/{driverid}/employer-inquiries")
def driver_employer_inquiries(driverid: str, user: dict = Depends(current_user),
                              conn: Connection = Depends(get_conn)):
    """Every previous employer who must be asked, every attempt made, and where each one stands."""
    acct = user["accountid"]
    # Kept, not discarded: the certification prints the driver's own details, and reading them
    # again after the commit below is exactly the mistake this function keeps attracting.
    driver = _applicant(conn, acct, driverid)
    # Seeding and reading happen on the same connection, so the commit comes last: committing in
    # the middle closes the transaction and everything after it fails.
    employers.ensure(conn, acct, driverid, createdby=user["recordid"])
    found = employers.for_driver(conn, acct, driverid)
    # The hand this user's requests will go out over. Their own signature shown back to them, so
    # the screen that sends a request shows what is about to be put on it - the drawn name only,
    # with nothing that would let it be used: the pair that unlocks it is never given out here.
    mine = _my_signature(conn, user, acct)
    # EVERY read happens before the commit: saved() closes the transaction, and anything after it
    # fails. This is the third time that has bitten this one function - if you are adding something
    # here, add it above this line.
    saved(conn)
    return {"inquiries": found, "channels": employers.CHANNELS,
            "complete": employers.complete(found), "dispositions": employers.DISPOSITIONS,
            # The five endings an investigation can have, named rather than numbered.
            "gfestatus": employers.GFE_STATUS, "gfeclosing": list(employers.GFE_CLOSING),
            # 391.23(d) gives 30 days from the start of employment. The screen is told when that
            # runs out so it can stop offering to ask rather than failing on the click.
            "window": employers.window(driver.get("hiredon"), localnow(user["timezone"]).date()),
            # Auto-filled on the certification: nobody retypes what the file already knows.
            "driver": {"name": f'{driver["firstname"]} {driver["lastname"]}'.strip().title(),
                       "drivernumber": driver.get("drivernumber"),
                       "hiredon": driver.get("hiredon")},
            # Who is certifying. There is no job title on a user - what TripProof knows is the
            # role they hold in this account, and printing that is honest where inventing a title
            # would not be.
            "certifier": {"name": user.get("name"), "title": user.get("role")},
            "signature": {"typedname": mine["typedname"], "fontkey": mine["fontkey"],
                          "signername": mine["signername"]} if mine else None}


class EmployerIn(BaseModel):
    employer: str
    contactname: str | None = None
    email: str | None = None
    fax: str | None = None
    phone: str | None = None
    address1: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    employedfrom: date | None = None
    employedthrough: date | None = None


@router.post("/drivers/{driverid}/employer-inquiries")
def add_employer_inquiry(driverid: str, body: EmployerIn, request: Request,
                         user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """An employer the application did not name, or one the office knows more about."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    rid = newid()
    run(conn, """
        INSERT INTO employerinquiries (recordid, accountid, driverid, employer, contactname, email,
                                       fax, phone, address1, city, state, zip, employedfrom,
                                       employedthrough, token, expireson, createdby)
        VALUES (:id, :a, :d, :name, :who, :em, :fax, :ph, :a1, :city, :st, :zip, :from_, :to_,
                :tok, :exp, :u)
    """, id=rid, a=acct, d=driverid, name=body.employer[:160], who=body.contactname,
        em=body.email, fax=body.fax, ph=body.phone, a1=body.address1, city=body.city,
        st=(body.state or "").upper()[:2] or None, zip=body.zip, from_=body.employedfrom,
        to_=body.employedthrough, tok=secrets.token_urlsafe(32),
        exp=utcnow() + timedelta(days=employers.VALID_DAYS), u=user["recordid"])
    log(conn, user, "create", "employerinquiry", driverid, {"employer": body.employer},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True, "recordid": rid}


def _inquiry(conn: Connection, accountid: str, driverid: str, inquiryid: str) -> dict:
    found = row(conn, """
        SELECT * FROM employerinquiries
        WHERE recordid = :i AND accountid = :a AND driverid = :d
    """, i=inquiryid, a=accountid, d=driverid)
    if not found:
        raise HTTPException(404, "No such inquiry on this driver")
    return found


class SendIn(BaseModel):
    # Where to send it. Defaulted from the employer on the screen and overridable there, because
    # the address on an application is the address the driver remembered - often a supervisor who
    # has moved on, and sometimes the only one that works is the one the office just looked up.
    to: str | None = None


def _my_signature(conn: Connection, user: dict, working: str | None = None) -> dict | None:
    """This user's signature of record.

    Looked for in their own account first and then in the account being worked in. A TripProof staff
    user has their own account, but a signature they adopted while acting inside a customer's file
    is stored against that customer - so one lookup finds it for an ordinary user and the other
    finds it for staff, and neither can reach anybody else's."""
    held = signatures.current(conn, user["accountid"], "user", user["recordid"])
    if not held and working and working != user["accountid"]:
        held = signatures.current(conn, working, "user", user["recordid"])
    return held


def _still_askable(conn: Connection, accountid: str, driverid: str, user: dict) -> None:
    """Refuse a request sent after the 30 days 391.23(d) allows.

    Applied to every way of asking - the email TripProof sends and the fax, letter or telephone
    call the office logs afterwards - because a rule enforced in one of them is not a rule."""
    driver = _applicant(conn, accountid, driverid)
    got = employers.window(driver.get("hiredon"), localnow(user["timezone"]).date())
    if not got["open"]:
        raise HTTPException(409, got["why"])


def _sign_request(conn: Connection, inq: dict, user: dict) -> None:
    """Put the sender's signature on the request, and refuse to send one nobody signed.

    A person signs with one signature - it is adopted once, behind a date of birth and a Social
    Security number, and used for everything they sign afterwards. So this is not a step the office
    repeats per employer: the signature already on file is applied, and somebody with none is told
    to create one rather than asked to type their name into this screen.

    It is stamped once per inquiry and stands for every attempt on it: a second fax of the same
    request is the same request, signed by the same person."""
    if inq.get("requestsignedon"):
        return
    # Looked up in the SIGNER'S account, not the driver's. A TripProof staff user acting inside a
    # customer's file has their own signature in their own account, and looking in the customer's
    # would never find it.
    held = _my_signature(conn, user, inq["accountid"])
    if not held:
        raise HTTPException(400, "Set up your signature before sending a request")
    run(conn, """
        UPDATE employerinquiries SET requestsignature = :sig, requestsignatureid = :sid,
               requestfontkey = :font, requestsignedby = :u, requestsignedon = :now
        WHERE recordid = :i
    """, sig=held["typedname"][:160], sid=held["recordid"], font=held["fontkey"][:24],
        u=user["recordid"], now=utcnow(), i=inq["recordid"])


@router.post("/drivers/{driverid}/employer-inquiries/{inquiryid}/email")
def email_employer_inquiry(driverid: str, inquiryid: str, body: SendIn, request: Request,
                           tasks: BackgroundTasks, user: dict = Depends(editor),
                           conn: Connection = Depends(get_conn)):
    """Send the employer the link, and record that it was sent. The sending IS the record."""
    acct = user["accountid"]
    _still_askable(conn, acct, driverid, user)
    driver = _applicant(conn, acct, driverid)
    inq = _inquiry(conn, acct, driverid, inquiryid)
    to = (body.to or inq["email"] or "").strip()
    if not to:
        raise HTTPException(400, "There is no email address for this employer")
    _sign_request(conn, inq, user)
    company = row(conn, "SELECT name FROM accounts WHERE recordid = :a", a=acct)["name"]
    subject, html, text = emails.employer_history_requested(
        employer=inq["employer"], accountname=company,
        driver=f'{driver["firstname"]} {driver["lastname"]}'.strip(),
        link=employers.link_for(inq["token"]), days=employers.VALID_DAYS)
    tasks.add_task(mailer.send, to, subject, html, text)
    # An address that worked once is the address to offer next time.
    if to != (inq["email"] or ""):
        run(conn, "UPDATE employerinquiries SET email = :em WHERE recordid = :i",
            em=to[:160], i=inquiryid)
    employers.record_attempt(conn, acct, inquiryid, channel="email", sentto=to,
                             outcome="sent", enteredby=user["recordid"])
    log(conn, user, "ask-employer", "driver", driverid,
        {"employer": inq["employer"], "channel": "email"}, ip=client_ip(request))
    saved(conn)
    return {"ok": True, "sentto": to, "link": employers.link_for(inq["token"])}


class AttemptIn(BaseModel):
    channel: str
    sentto: str | None = None
    outcome: str | None = None
    note: str | None = None
    senton: date | None = None


@router.post("/drivers/{driverid}/employer-inquiries/{inquiryid}/attempts")
def record_employer_attempt(driverid: str, inquiryid: str, body: AttemptIn, request: Request,
                            user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """An attempt made outside TripProof - a fax, a letter, a telephone call.

    Not a lesser kind of record: 391.23(i) asks what the carrier did, not what this software did."""
    acct = user["accountid"]
    _still_askable(conn, acct, driverid, user)
    inq = _inquiry(conn, acct, driverid, inquiryid)
    if body.channel not in employers.CHANNELS:
        raise HTTPException(400, "Say how the employer was contacted")
    # A request sent by fax or post is the same request, and is signed the same way.
    _sign_request(conn, inq, user)
    employers.record_attempt(
        conn, acct, inquiryid, channel=body.channel, sentto=body.sentto, note=body.note,
        outcome=body.outcome, enteredby=user["recordid"],
        senton=datetime.combine(body.senton, time()) if body.senton else None)
    # A fax number nobody had recorded is worth keeping once somebody has used it.
    if body.channel == "fax" and (body.sentto or "").strip():
        run(conn, "UPDATE employerinquiries SET fax = COALESCE(fax, :fax) WHERE recordid = :i",
            fax=body.sentto.strip()[:40], i=inquiryid)
    log(conn, user, "employer-attempt", "driver", driverid,
        {"employer": inq["employer"], "channel": body.channel}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class EffortIn(BaseModel):
    status: str | None = None
    note: str | None = None


class ReviewIn(BaseModel):
    # Reading it is the act. A disposition is kept where somebody records one, but the requirement
    # turns on whether a person here has read the reply, not on them classifying it.
    disposition: str | None = None
    comments: str | None = None


@router.post("/drivers/{driverid}/employer-inquiries/{inquiryid}/review")
def review_employer_reply(driverid: str, inquiryid: str, body: ReviewIn, request: Request,
                          user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Record that somebody here read the reply, and what they decided about it - SPHI section 9.

    A reply arrives from outside: it may say the driver was dismissed, or that there are accidents
    on their record. Until this, the requirement reads as waiting rather than met, however complete
    the answer looks."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    inq = _inquiry(conn, acct, driverid, inquiryid)
    if not inq["respondedon"]:
        raise HTTPException(409, "This employer has not answered yet")
    if body.disposition and body.disposition not in employers.DISPOSITIONS:
        raise HTTPException(400, "Unrecognised disposition")
    run(conn, """
        UPDATE employerinquiries SET disposition = :d, reviewcomments = :c, reviewedon = :now,
               reviewedby = :u
        WHERE recordid = :i
    """, d=body.disposition, c=((body.comments or "").strip().upper() or None), now=utcnow(),
        u=user["recordid"], i=inquiryid)
    log(conn, user, "employer-review", "driver", driverid,
        {"employer": inq["employer"], "disposition": body.disposition}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/drivers/{driverid}/employer-inquiries/{inquiryid}/good-faith")
def close_employer_inquiry(driverid: str, inquiryid: str, body: EffortIn, request: Request,
                           user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Certify how this investigation ended - 49 CFR 391.23(i).

    Three things make this a record rather than a note: it says which of the five endings happened,
    it stands on attempts that were actually made, and somebody signs it.

    The signature is the signer's own, already on file - adopted once behind a date of birth and a
    Social Security number and applied to everything they sign. Nobody types their name into this
    form, and somebody with no signature is told to set one up rather than asked to improvise."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    inq = _inquiry(conn, acct, driverid, inquiryid)
    status = (body.status or "noresponse").strip().lower()
    if status not in employers.GFE_STATUS:
        raise HTTPException(400, "Say how the investigation ended")
    closing = status in employers.GFE_CLOSING
    if closing and status != "received" and inq["respondedon"]:
        raise HTTPException(409, "This employer has already answered")
    # Signing off an effort nobody made is the one thing the attempts table exists to prevent.
    if closing and status != "received" and not employers.attempts(conn, inquiryid):
        raise HTTPException(400, "Record at least one attempt before closing this as an effort")

    held = None
    if closing:
        # The signer's own account, not the driver's: a TripProof staff user working inside a
        # customer's file has their signature in their own account.
        held = _my_signature(conn, user, inq["accountid"])
        if not held:
            raise HTTPException(400, "Set up your signature before certifying an effort")
    run(conn, """
        UPDATE employerinquiries
           SET effortstatus = :st, effortnote = :n,
               effortclosedon = :closed, effortclosedby = :u,
               effortsignature = :sig, effortsignatureid = :sid, effortfontkey = :font,
               effortsignedon = :signed
         WHERE recordid = :i
    """, st=status, n=(body.note or None), closed=(utcnow() if closing else None),
        u=(user["recordid"] if closing else None),
        sig=(held["typedname"][:160] if held else None),
        sid=(held["recordid"] if held else None),
        font=(held["fontkey"][:24] if held else None),
        signed=(utcnow() if held else None), i=inquiryid)
    # Drawn now, from what was just certified - not rebuilt later from columns that may have moved.
    if closing:
        gfeview.keep(conn, inquiryid, user)
    log(conn, user, "employer-gfe", "driver", driverid,
        {"employer": inq["employer"], "status": status}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "evaluation": evaluation}


@router.post("/drivers/{driverid}/employer-inquiries/{inquiryid}/response")
async def file_employer_response(driverid: str, inquiryid: str, request: Request,
                                 respondedby: str | None = Form(None),
                                 note: str | None = Form(None),
                                 file: UploadFile | None = File(None),
                                 user: dict = Depends(editor),
                                 conn: Connection = Depends(get_conn)):
    """A reply that came back on paper or by fax, filed by the office."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    inq = _inquiry(conn, acct, driverid, inquiryid)
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.THIRDPARTY)
    run(conn, """
        UPDATE employerinquiries SET respondedon = :now, respondedby = :who,
               responsenote = COALESCE(:n, responsenote), documentid = COALESCE(:doc, documentid)
        WHERE recordid = :i
    """, now=utcnow(), who=(respondedby or None), n=(note or None), doc=documentid, i=inquiryid)
    employers.record_attempt(conn, acct, inquiryid, channel="mail", outcome="answered",
                             note="Reply filed by the office", enteredby=user["recordid"])
    _filed_here(conn, acct, driverid, "employerinquiries", inquiryid, user["recordid"])
    log(conn, user, "employer-reply", "driver", driverid, {"employer": inq["employer"]},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/drivers/{driverid}/upload-requests")
def ask_for_a_document(driverid: str, body: UploadRequestIn, request: Request,
                       tasks: BackgroundTasks, user: dict = Depends(editor),
                       conn: Connection = Depends(get_conn)):
    """Ask this driver for a document only they hold, and send them the link.

    The link is answered here too, so the office can read it out to somebody with no email - the
    same way a signing request works, and for the same reason."""
    acct = user["accountid"]
    driver = row(conn, """
        SELECT recordid, firstname, lastname, email FROM drivers
        WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=driverid, a=acct)
    if not driver:
        raise HTTPException(404, "No such driver")
    made = uploading.create(conn, acct, driverid, body.code, user["recordid"])
    company = row(conn, "SELECT name FROM accounts WHERE recordid = :a", a=acct)["name"]
    if driver["email"]:
        run(conn, "UPDATE uploadrequests SET sentto = :to, senton = :now WHERE recordid = :id",
            to=driver["email"], now=utcnow(), id=made["recordid"])
        subject, html, text = emails.document_requested(
            name=f'{driver["firstname"]} {driver["lastname"]}'.strip(), accountname=company,
            document=made["document"], link=made["link"], days=made["days"])
        tasks.add_task(mailer.send, driver["email"], subject, html, text)
    log(conn, user, "ask-upload", "driver", driverid, {"code": body.code}, ip=client_ip(request))
    saved(conn)
    return {"ok": True, "link": made["link"], "sentto": driver["email"], "days": made["days"]}


@router.get("/drivers/{driverid}/upload-requests")
def outstanding_document_requests(driverid: str, user: dict = Depends(current_user),
                                  conn: Connection = Depends(get_conn)):
    """What this driver has been asked for and has not sent yet."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    return {"requests": [{**r, "link": uploading.link_for(r["token"])} for r in rows(conn, """
        SELECT recordid, credentialcode, token, sentto, senton, expireson, createdon
        FROM uploadrequests
        WHERE accountid = :a AND driverid = :d AND uploadedon IS NULL AND cancelledon IS NULL
        ORDER BY createdon DESC
    """, a=acct, d=driverid)]}


@router.post("/drivers/{driverid}/sent-documents/{documentid}/reviewed")
def mark_sent_document_read(driverid: str, documentid: str, request: Request,
                            user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Somebody in the office has read a document the driver sent in.

    Until this, the requirement it answers reads as waiting rather than met - see migration 132. It
    is recorded against the request, which is the one thing that knows the document came from the
    driver, so it holds whatever kind of record the document became."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    # What was asked for, read before the update, because the line in the history has to say which
    # document was read. "A document was read" is not an audit entry.
    asked = row(conn, """
        SELECT credentialcode FROM uploadrequests
        WHERE accountid = :a AND driverid = :d AND documentid = :doc
    """, a=acct, d=driverid, doc=documentid) or {}
    n = run(conn, """
        UPDATE uploadrequests SET reviewedon = :now, reviewedby = :u
        WHERE accountid = :a AND driverid = :d AND documentid = :doc AND reviewedon IS NULL
    """, now=utcnow(), u=user["recordid"], a=acct, d=driverid, doc=documentid).rowcount
    if not n:
        raise HTTPException(404, "There is nothing waiting to be checked against that document")
    log(conn, user, "reviewed-sent-document", "driver", driverid,
        {"documentid": documentid, "code": asked.get("credentialcode")}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/drivers/{driverid}/upload-requests/{requestid}/cancel")
def cancel_document_request(driverid: str, requestid: str, request: Request,
                            user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Withdraw a request. The link stops working; the row stays, because somebody asked."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    held = row(conn, """
        SELECT credentialcode FROM uploadrequests
        WHERE recordid = :id AND accountid = :a AND driverid = :d
    """, id=requestid, a=acct, d=driverid) or {}
    n = run(conn, """
        UPDATE uploadrequests SET cancelledon = :now
        WHERE recordid = :id AND accountid = :a AND driverid = :d
          AND uploadedon IS NULL AND cancelledon IS NULL
    """, now=utcnow(), id=requestid, a=acct, d=driverid).rowcount
    if not n:
        raise HTTPException(404, "There is no such request outstanding")
    log(conn, user, "cancel-upload-request", "driver", driverid,
        {"code": held.get("credentialcode")}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.get("/drivers/{driverid}/signing-requests")
def outstanding_signature_requests(driverid: str, user: dict = Depends(current_user),
                                   conn: Connection = Depends(get_conn)):
    """What this driver has been asked to sign and has not signed yet."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    return {"requests": [{**r, "link": signing.link_for(r["token"])} for r in rows(conn, """
        SELECT recordid, doctype, token, sentto, senton, expireson, createdon
        FROM signingrequests
        WHERE accountid = :a AND driverid = :d AND signedon IS NULL AND cancelledon IS NULL
        ORDER BY createdon DESC
    """, a=acct, d=driverid)]}


@router.post("/drivers/{driverid}/signed/{doctype}/reviewed")
def mark_signed_read(driverid: str, doctype: str, request: Request,
                     user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Somebody in the office has read a document the driver signed down a link.

    The third of the three ways something arrives from outside, and it is recorded in the same
    place as the other two: against the request, which is the one row that knows it came from
    outside at all."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    n = run(conn, """
        UPDATE signingrequests SET reviewedon = :now, reviewedby = :u
        WHERE accountid = :a AND driverid = :d AND doctype = :t
          AND signedon IS NOT NULL AND reviewedon IS NULL
    """, now=utcnow(), u=user["recordid"], a=acct, d=driverid, t=doctype).rowcount
    if not n:
        raise HTTPException(404, "There is nothing waiting to be checked for that document")
    log(conn, user, "reviewed-signed", "driver", driverid, {"doctype": doctype},
        ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "evaluation": evaluation}


# ------------------------------------------------------------------------------------------------
# Section 2 of the I-9 - 8 CFR 274a.2(b)(1)(ii)
#
# The employee signs Section 1. The employer examines their documents and certifies Section 2, and
# that is a different person making a different statement under penalty of perjury. Reading the
# form is not certifying it, so this is its own act with its own signature rather than something
# that happens quietly when somebody clicks Reviewed.
#
# Nothing in the certification is typed. The company is the company on file, the first day of work
# is the hire date on the driver's record, and the name and title are the account of whoever is
# signing. What is left for a person to do is the only part that is theirs: looking at the
# documents, and putting their name to having looked.
# ------------------------------------------------------------------------------------------------

def _i9_request(conn: Connection, acct: str, driverid: str) -> dict:
    held = row(conn, """
        SELECT recordid, documentid, signedon, certifiedon
        FROM signingrequests
        WHERE accountid = :a AND driverid = :d AND doctype = 'I9' AND signedon IS NOT NULL
          AND cancelledon IS NULL
        ORDER BY signedon DESC LIMIT 1
    """, a=acct, d=driverid)
    if not held:
        raise HTTPException(404, "This driver has not signed an I-9")
    return held


def _employer_block(conn: Connection, acct: str, driver: dict, user: dict) -> dict:
    """What goes in the Section 2 boxes, from what is already on file."""
    # The same company block the W-4 is filled from, so the two forms cannot give an auditor two
    # different addresses for one employer on the same day.
    company = pdfform.company(conn, acct)
    # The form asks for the certifier's title. The account knows what they are allowed to do here,
    # which is the nearest thing on file to a job title, and it is said in the words the office
    # uses rather than the word the database stores.
    title = {"owner": "Owner", "admin": "Administrator", "editor": "Safety Administrator",
             "viewer": "Authorized Representative"}.get(user.get("role") or "",
                                                        "Authorized Representative")
    # The box asks for the name surname-first, which is not how the account stores it. The account
    # holds one name field, so the surname is taken to be the last word of it - the ordinary
    # reading, and the only one available without asking everybody to re-enter their name in two
    # halves. A one-word name is left as it is rather than turned into a surname with nothing
    # in front of it.
    parts = (user["name"] or "").split()
    surnamefirst = f'{parts[-1]}, {" ".join(parts[:-1])}' if len(parts) > 1 else (user["name"] or "")
    last = (driver.get("lastname") or "").strip()
    return {
        "who": f"{surnamefirst} - {title}",
        "signer": user["name"],
        "title": title,
        "orgname": company["orgname"],
        "orgaddress": company["orgaddress"],
        "firstday": str(driver.get("hiredon") or "") or None,
        "employee": f'{(driver.get("firstname") or "").strip()} {last}'.strip().title(),
    }


@router.get("/drivers/{driverid}/signed/I9/certification")
def i9_certification(driverid: str, user: dict = Depends(current_user),
                     conn: Connection = Depends(get_conn)):
    """What will be written into Section 2, so it can be read before it is signed."""
    acct = user["accountid"]
    driver = _applicant(conn, acct, driverid)
    held = _i9_request(conn, acct, driverid)
    block = _employer_block(conn, acct, driver, user)
    return {**block, "certifiedon": str(held["certifiedon"]) if held["certifiedon"] else None,
            # Nothing on file says which identity documents were examined, and the form must not
            # guess: an employer that invents a document title has attested to seeing a document
            # it never saw. Said here so the screen can say it rather than leave it unexplained.
            "listsblank": True}


class CertifyI9(BaseModel):
    signatureid: str


@router.post("/drivers/{driverid}/signed/I9/certify")
def certify_i9(driverid: str, body: CertifyI9, request: Request,
               user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Write Section 2 onto the form the employee signed, and sign it."""
    acct = user["accountid"]
    driver = _applicant(conn, acct, driverid)
    if driver["status"] != "hired":
        raise HTTPException(409, "Section 2 is certified once the driver is on the roster")
    held = _i9_request(conn, acct, driverid)
    if held["certifiedon"]:
        raise HTTPException(409, "Section 2 has already been certified")
    if not held["documentid"]:
        raise HTTPException(409, "The signed I-9 is not on file")
    # The signature is the one they proved was theirs a moment ago, not a name typed into a box.
    sig = signatures.current(conn, acct, "user", user["recordid"])
    if not sig or sig["recordid"] != body.signatureid:
        raise HTTPException(409, "Certify the form with your own signature")

    doc = row(conn, "SELECT storagekey, filename FROM documents WHERE recordid = :id",
              id=held["documentid"])
    if not doc:
        raise HTTPException(409, "The signed I-9 is not on file")
    try:
        filed = storage.get(doc["storagekey"])
    except storage.Missing:
        raise HTTPException(409, "The signed I-9 is no longer stored")

    block = _employer_block(conn, acct, driver, user)
    recordid = newid()
    now = utcnow()
    certified = i9.certify(
        filed, block, signature=sig["typedname"], fontkey=sig["fontkey"],
        signedon=localnow(user["timezone"]).date(),
        stamp={"recordid": recordid, "signedon": str(now), "ip": client_ip(request)})

    name = block["employee"].lower().replace(" ", "-")
    documentid = storage.keep(conn, acct, "documents", certified, f"i9-{name}-certified.pdf",
                              "application/pdf", user["recordid"], origin=storage.OFFICE)
    # The certifier's own signature, against the file they certified. Hashed on the FILE, as the
    # employee's was: there is no text behind an official form to hash.
    signatures.sign(conn, acct, sig["recordid"], "I9", driverid, "", ownertype="user",
                    version=documents.DRIVER_DOC_VERSION,
                    contenthash=hashlib.sha256(certified).hexdigest(), recordid=recordid,
                    ip=client_ip(request), useragent=request.headers.get("user-agent"))
    run(conn, """
        UPDATE signingrequests
           SET employeedocumentid = COALESCE(employeedocumentid, documentid),
               documentid = :new, certifiedon = :now, certifiedby = :u,
               certificationsigid = :sig,
               -- Certifying it is reading it. Somebody who has attested under penalty of perjury
               -- that they examined this form has plainly read it, and leaving it in the review
               -- queue afterwards would ask them to say so twice.
               reviewedon = COALESCE(reviewedon, :now), reviewedby = COALESCE(reviewedby, :u)
         WHERE recordid = :id
    """, new=documentid, now=now, u=user["recordid"], sig=sig["recordid"], id=held["recordid"])
    log(conn, user, "i9-certified", "driver", driverid, {"documentid": documentid},
        ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "documentid": documentid, "evaluation": evaluation}


# ------------------------------------------------------------------------------------------------
# The road test - 49 CFR 391.31
#
# One event with one output. The office opens it and sends it to an examiner; the examiner does the
# test and signs; what comes back is read here like anything else from outside.
# ------------------------------------------------------------------------------------------------

@router.get("/drivers/{driverid}/road-tests")
def driver_road_tests(driverid: str, user: dict = Depends(current_user),
                      conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    return {"tests": roadtest.for_driver(conn, acct, driverid),
            "items": [{"key": k, "label": l} for k, l in roadtest.ITEMS],
            "extras": [{"key": k, "label": l} for k, l in roadtest.EXTRAS],
            "ratings": roadtest.RATINGS, "results": roadtest.RESULTS,
            "vehicletypes": roadtest.VEHICLE_TYPES}


class ExaminerIn(BaseModel):
    name: str
    email: str
    title: str | None = None
    organization: str | None = None


@router.post("/drivers/{driverid}/road-tests")
def send_road_test(driverid: str, body: ExaminerIn, request: Request, tasks: BackgroundTasks,
                   user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Open a road test and send the examiner the link that administers it."""
    acct = user["accountid"]
    driver = _applicant(conn, acct, driverid)
    to = (body.email or "").strip().lower()
    if "@" not in to:
        raise HTTPException(400, "An email address is needed to send the examiner the link")
    rid = roadtest.create(conn, acct, driverid, user["recordid"])
    run(conn, """
        UPDATE roadtests SET examinername = :n, examineremail = :e, examinertitle = :t,
               examinerorg = :o, sentto = :e, senton = :now
        WHERE recordid = :i
    """, n=body.name.strip().upper()[:128], e=to[:190],
        t=((body.title or "").strip().upper()[:128] or None),
        o=((body.organization or "").strip().upper()[:160] or None), now=utcnow(), i=rid)
    held = row(conn, "SELECT token FROM roadtests WHERE recordid = :i", i=rid)
    company = row(conn, "SELECT name FROM accounts WHERE recordid = :a", a=acct)["name"]
    who = f'{driver["firstname"]} {driver["lastname"]}'.strip().title()
    subject, html, text = emails.road_test_requested(
        examiner=body.name.strip(), accountname=company, driver=who,
        link=roadtest.link_for(held["token"]), days=roadtest.VALID_DAYS)
    tasks.add_task(mailer.send, to, subject, html, text)
    log(conn, user, "road-test-sent", "driver", driverid, {"sentto": to}, ip=client_ip(request))
    saved(conn)
    return {"recordid": rid, "link": roadtest.link_for(held["token"])}


@router.post("/drivers/{driverid}/road-tests/{recordid}/reviewed")
def mark_road_test_read(driverid: str, recordid: str, request: Request,
                        user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Somebody here has read what the examiner sent back."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    n = run(conn, """
        UPDATE roadtests SET reviewedon = :now, reviewedby = :u
        WHERE recordid = :i AND accountid = :a AND driverid = :d
          AND completedon IS NOT NULL AND reviewedon IS NULL
    """, now=utcnow(), u=user["recordid"], i=recordid, a=acct, d=driverid).rowcount
    if not n:
        raise HTTPException(404, "There is nothing waiting to be checked on that road test")
    log(conn, user, "road-test-reviewed", "driver", driverid, {"recordid": recordid},
        ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "evaluation": evaluation}


@router.get("/drivers/{driverid}/asks")
def driver_asks(driverid: str, doctype: str | None = None, code: str | None = None,
                user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Everything this driver has been asked for, answered or not.

    The outstanding-request endpoints answer "is something in flight"; this answers "what have we
    asked them, and when" - which is a different question and the one somebody asks before chasing
    a driver for the fourth time. Both kinds of asking are here because the office does not think
    of them as two things: a signature and an upload are both a link sent to a driver."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    asks = []
    if doctype:
        asks += [{**r, "kind": "signature", "what": r["doctype"],
                  "link": signing.link_for(r["token"])}
                 for r in rows(conn, """
            SELECT recordid, doctype, token, sentto, senton, createdon, expireson,
                   signedon AS answeredon, cancelledon
            FROM signingrequests
            WHERE accountid = :a AND driverid = :d AND doctype = :t
            ORDER BY createdon DESC
        """, a=acct, d=driverid, t=doctype)]
    if code:
        asks += [{**r, "kind": "upload", "what": r["credentialcode"],
                  "link": uploading.link_for(r["token"])}
                 for r in rows(conn, """
            SELECT recordid, credentialcode, token, sentto, senton, createdon, expireson,
                   uploadedon AS answeredon, cancelledon, reviewedon
            FROM uploadrequests
            WHERE accountid = :a AND driverid = :d AND credentialcode = :c
            ORDER BY createdon DESC
        """, a=acct, d=driverid, c=code)]
    asks.sort(key=lambda x: x["createdon"], reverse=True)
    return {"asks": asks}


@router.get("/drivers/{driverid}/signed")
def driver_signed(driverid: str, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Everything this driver has signed - the application itself, the policies, the consents."""
    _applicant(conn, user["accountid"], driverid)
    # What this driver put their name to. An annual review is signed by the office about them, not
    # by them, so it is not on this list - it belongs to the review of the record it was made on.
    acct = user["accountid"]
    return {"documents": applicationview.signed_list(conn, acct, driverid)}


def _safe(name: str) -> str:
    """A filename a zip can carry on any machine that opens it."""
    keep = "".join(c if (c.isalnum() or c in " .-_") else "-" for c in (name or "file"))
    return " ".join(keep.split())[:120] or "file"


@router.get("/drivers/{driverid}/files.zip")
def download_driver_file(driverid: str, request: Request, user: dict = Depends(current_user),
                         conn: Connection = Depends(get_conn)):
    """The whole driver file, zipped.

    Everything the Driver Files screen lists, in the same sections, as folders. Two kinds of
    thing go in: documents held in the store, and the documents that are REBUILT from the record
    rather than stored - the acknowledgements, the annual reviews - which are written into the
    zip as the pages they render to. A file somebody downloads to hand to an auditor cannot be
    missing the half of it that happens to be generated.

    Nothing new is produced here and nothing is re-derived: each piece is fetched exactly the way
    the screen fetches it, so what is in the zip is what is on the screen.
    """
    acct = user["accountid"]
    driver = _applicant(conn, acct, driverid)
    who = f'{driver["firstname"]} {driver["lastname"]}'.strip().title() or "driver"
    sections = driver_files(driverid, user, conn)["sections"]

    buf = io.BytesIO()
    missing = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for sec in sections:
            for n, f in enumerate(sec["files"], 1):
                folder = _safe(sec["name"])
                if f["kind"] == "file":
                    doc = row(conn, "SELECT filename, storagekey FROM documents "
                                    "WHERE recordid = :id AND accountid = :a",
                              id=f["recordid"], a=acct)
                    if not doc:
                        continue
                    try:
                        data = storage.get(doc["storagekey"])
                    except storage.Missing:
                        missing.append(f'{sec["name"]}/{doc["filename"]}')
                        continue
                    zf.writestr(f'{folder}/{n:02d} {_safe(doc["filename"])}', data)
                    continue
                # Rebuilt rather than stored. Served as its own page, so that is what goes in.
                doctype = f["doctype"]
                if doctype.startswith("ANNUAL_REVIEW:"):
                    view = annualreview.sheet(conn, acct, driverid, doctype.split(":", 1)[1])
                else:
                    view = applicationview.signed_document(conn, acct, driverid, doctype)
                if not view:
                    missing.append(f'{sec["name"]}/{f["what"]}')
                    continue
                # A form signed on the government's own paper is a stored PDF after all.
                if view.get("documentid"):
                    doc = row(conn, "SELECT filename, storagekey FROM documents "
                                    "WHERE recordid = :id AND accountid = :a",
                              id=view["documentid"], a=acct)
                    try:
                        zf.writestr(f'{folder}/{n:02d} {_safe(doc["filename"])}',
                                    storage.get(doc["storagekey"]))
                        continue
                    except (TypeError, storage.Missing):
                        missing.append(f'{sec["name"]}/{f["what"]}')
                        continue
                html = (f'<!doctype html><meta charset="utf-8">'
                        f'<title>{escape(view.get("title") or f["what"])}</title>'
                        f'<style>{view.get("css") or ""}</style>{view.get("html") or ""}')
                zf.writestr(f'{folder}/{n:02d} {_safe(f["what"])}.html', html.encode())
        # What could NOT be included, named, inside the zip itself. A download that quietly
        # leaves something out is worse than one that says what is missing.
        if missing:
            zf.writestr("MISSING.txt",
                        ("These are listed on the driver's file but their stored copy could not "
                         "be read:\n\n" + "\n".join(missing) + "\n").encode())

    log(conn, user, "download-driver-file", "driver", driverid,
        {"files": sum(len(s["files"]) for s in sections), "missing": len(missing)},
        ip=client_ip(request))
    saved(conn)
    stamp = date.today().isoformat()
    return Response(buf.getvalue(), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{_safe(who)} - driver file {stamp}.zip"'})


@router.get("/drivers/{driverid}/signed/{doctype}")
def driver_signed_document(driverid: str, doctype: str, request: Request,
                           user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """One of them, as it was signed: the wording shown at the time, the signature, and the stamp."""
    _applicant(conn, user["accountid"], driverid)
    if doctype.startswith("ANNUAL_REVIEW:"):
        view = annualreview.sheet(conn, user["accountid"], driverid, doctype.split(":", 1)[1])
    else:
        view = applicationview.signed_document(conn, user["accountid"], driverid, doctype)
    if not view:
        raise HTTPException(404, "This driver has not signed that")
    log(conn, user, "view", "signeddocument", driverid, {"doctype": doctype}, ip=client_ip(request))
    saved(conn)
    return view


@router.get("/drivers/{driverid}/application.pdf")
def driver_application_pdf(driverid: str, request: Request, user: dict = Depends(current_user),
                           conn: Connection = Depends(get_conn)):
    """The same sheets, drawn to PDF so they can be printed or filed as one document."""
    view = applicationview.application_for(conn, user["accountid"], driverid)
    if not view:
        raise HTTPException(404, "This driver has no online application")
    log(conn, user, "print", "driverapplication", driverid, ip=client_ip(request))
    pdf = applicationview.to_pdf(view, applicationview.signature_css())
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="driver-application.pdf"'})


# What the log's own words mean to somebody reading a driver's history.
#
# Each line names the THING first and says what happened to it - "The PHI confidentiality
# acknowledgment was signed by the driver" rather than "Signed a document". A reader scanning a
# year of history is looking for a document, not for a verb, and a sentence that makes them read
# the small print to find out which document is a sentence that wasted their time.
#
# Each entry is (template, who did it). `{what}` is the thing, filled from the log's payload; where
# the payload does not name one, the fallback after the pipe is used instead.
ACTIVITY_WORDS = {
    # The driver, on their own application
    "driverapply-start": ("{by} opened their application and proved who they were", "driver"),
    "driverapply-resume": ("{by} came back to their application", "driver"),
    "driverapply-signature": ("{by} adopted their signature", "driver"),
    "driverapply-submit": ("{by} submitted their application", "driver"),
    "apply-card-verified": ("{by} proved their identity to open the application", "driver"),
    "apply-complete": ("{by} finished their application", "driver"),
    # The driver, answering something the office sent them
    "signed-on-request": ("{what} was signed by {by}|A document was signed by {by}", "driver"),
    "uploaded-on-request": ("{what} was sent in by {by}|A document was sent in by {by}", "driver"),
    "answered-on-request": ("{what} was answered by {by}|A question was answered by {by}", "driver"),
    # The office, on the application
    "driverapplication-pending": ("The application was moved to pending by {by}", "office"),
    "driverapplication-declined": ("The driver was marked not hired by {by}", "office"),
    "driverapplication-returned": ("The application was sent back for corrections by {by}",
                                   "office"),
    "driverapplication-hired": ("The driver was hired by {by}", "office"),
    "driver-deactivated": ("The driver was taken off the roster by {by}", "office"),
    "view": ("{what} was opened by {by}|The application was opened by {by}", "office"),
    "print": ("The application was printed by {by}", "office"),
    "create": ("{what} was added by {by}|A record was added by {by}", "office"),
    "update": ("{what} was changed by {by}|A record was changed by {by}", "office"),
    "delete": ("{what} was deleted by {by}|A record was deleted by {by}", "office"),
    # The office, working the file
    "ask-upload": ("{what} was requested from the driver by {by}|A document was requested from the "
                   "driver by {by}", "office"),
    "cancel-upload-request": ("{what} was withdrawn by {by}|A request to the driver was withdrawn "
                              "by {by}", "office"),
    "signature-requested": ("{what} was sent to the driver to sign by {by}|A document was sent to "
                            "the driver to sign by {by}", "office"),
    "signature-adopted": ("A signature was adopted by {by}", "office"),
    "licencecopy": ("A copy of the driver's license was filed by {by}", "office"),
    "requirement-document": ("{what} was filed against a requirement by {by}|A document was filed "
                             "against a requirement by {by}", "office"),
    "requirement-verified": ("{what} was read by {by} and accepted as answering the requirement|A "
                             "document was read and accepted by {by}", "office"),
    "reviewed-sent-document": ("{what} the driver sent in was read by {by}|A document the driver "
                               "sent in was read by {by}", "office"),
    "reviewed-signed": ("{what} was read by {by} after the driver signed it|A signed document was "
                        "read by {by}", "office"),
    "reviewed": ("{what} was read by {by} and found {finding}|A record was read by {by}",
                 "office"),
    # The annual review of the driving record under 49 CFR 391.25, not a review of "a record".
    "review": ("The annual review of the driving record was recorded by {by} and found {finding}|"
               "The annual review of the driving record was recorded by {by}", "office"),
    "review-filed": ("An annual review of the driving record was filed by {by}", "office"),
    "order": ("{what} was sent away for by {by}|A record was sent away for by {by}", "office"),
    "file": ("{what} was filed by {by}|A record that came back was filed by {by}", "office"),
    "cancel": ("{what} was cancelled by {by}|An order was cancelled by {by}", "office"),
    "evaluate": ("The driver's requirements were re-evaluated", "office"),
    # A requirement settled by something known rather than by a document - age, English
    # proficiency - where the carrier makes the determination and there is nothing to file.
    "determination": ("{what} was answered by {by}|A requirement was answered by {by}", "office"),
    # Which register, and what it said. The two federal registers were split apart on purpose -
    # OIG LEIE and SAM.gov answer different questions - so a line that says only "an exclusion
    # screening" undoes the split for anybody reading the history back.
    "exclusion-check": ("{what} was run by {by} and came back {finding}|An exclusion screening was "
                        "run by {by}", "office"),
    "exclusion-settled": ("{what} was settled by {by} as {finding}|A possible exclusion match was "
                          "settled by {by}", "office"),
    "exclusion-reinstated": ("{what} was recorded as reinstated by {by}|A reinstatement was "
                             "recorded by {by}", "office"),
    "drugtest": ("{what} was filed by {by}|A drug or alcohol test result was filed by {by}",
                 "office"),
    "prohibit": ("A prohibition on safety-sensitive work was recorded by {by}, on {what}|A "
                 "prohibition on safety-sensitive work was recorded by {by}", "office"),
    "rtd": ("The return-to-duty process was recorded by {by}", "office"),
    "supervisor-training-signed": ("{by} signed their reasonable suspicion training record",
                                   "office"),
    "test-withdrawn": ("A drug or alcohol test was withdrawn by {by}", "office"),
    "accident-withdrawn": ("An accident was withdrawn from the register by {by}", "office"),
    "file-withdrawn": ("A file was withdrawn from the driver's folder by {by}", "office"),
    "randompool": ("Random testing pool membership was set by {by}", "office"),
    "employment-decision": ("The employment decision after a violation was recorded by {by}",
                            "office"),
    "accident": ("The accident of {what} was recorded by {by}|An accident was recorded by {by}",
                 "office"),
    "accident-amended": ("Outstanding questions about the accident of {what} were answered by {by}|"
                         "Outstanding questions about an accident were answered by {by}", "office"),
    "ask-employer": ("{what} was asked for the safety performance history by {by}|A previous "
                     "employer was asked for the safety performance history by {by}", "office"),
    "employer-attempt": ("An attempt to reach {what} was logged by {by}|An attempt to reach a "
                         "previous employer was logged by {by}", "office"),
    "employer-review": ("The reply from {what} was read by {by}|A previous employer's reply was "
                        "read by {by}", "office"),
    "employer-gfe": ("A good faith effort was certified for {what} by {by}|A good faith effort was "
                     "certified by {by}", "office"),
    "road-test-sent": ("The road test was sent to {what} to administer by {by}|The road test was "
                       "sent to an examiner to administer by {by}", "office"),
    "road-test-reviewed": ("The completed road test was read by {by}", "office"),
    "download": ("{what} was downloaded by {by}|A document was downloaded by {by}", "office"),
    "export": ("The driver file was exported by {by}", "office"),
    "open": ("{what} was opened by {by}|A record was opened by {by}", "office"),
    "answer": ("{what} was answered by {by}|A company question was answered by {by}", "office"),
    # From outside
    "employer-reply": ("{what} answered the safety performance history request|A previous employer "
                       "answered the safety performance history request", "outside"),
}

# The credential and report codes as people say them, where the code is not already readable.
SUBJECT_WORDS = {
    "DRIVER_LICENSE": "The driver's license",
    "DOT_MEDICAL_CARD": "The medical certificate",
    "PREEMP_DA_QUESTIONNAIRE": "The pre-employment drug and alcohol questionnaire",
    "RTD_DOCUMENTATION": "The return-to-duty documentation",
    "CLEARINGHOUSE_PREEMP": "The Clearinghouse pre-employment query",
    "PSP_REPORT": "The PSP report",
    "CDLIS_CHECK": "The CDLIS report",
    "ROAD_TEST": "The road test",
}


def _thing(title: str) -> str:
    """A document's title as it reads mid-sentence: "The medical certificate", but "The PHI
    confidentiality acknowledgment" - an acronym keeps its capitals, which is why this is not a
    bare lower() on the first letter."""
    if not title:
        return title
    # A title that already opens with an article keeps it. "A Summary of Your Rights Under the Fair
    # Credit Reporting Act" is the document's name; "The a Summary of Your Rights" is nothing.
    if title.split(" ", 1)[0].lower() in ("a", "an", "the"):
        return title
    if len(title) > 1 and title[1].isupper():
        return f"The {title}"
    return f"The {title[0].lower()}{title[1:]}"


def _subject(action: str, d: dict, names: dict | None = None) -> str | None:
    """What the line is ABOUT, in words, from whatever the log's payload carries.

    `names` is what the codes are called - requirement names and credential names read from the
    catalog by the caller. Without it a code falls back to its own spelling in title case, and
    "Prior Violation Rtd" is not what anything is called."""
    if not d:
        return None
    # Which register was searched. Gated on the action because `source` means something else on a
    # prohibition - where the bar came from - and the two must not borrow each other's words.
    if action.startswith("exclusion") and d.get("source"):
        return EXCLUSION_WORDS.get(d["source"], d["source"].replace("_", " ").title())
    if action == "prohibit" and d.get("source"):
        return PROHIBITION_WORDS.get(d["source"], d["source"])
    if action in ("accident", "accident-amended") and d.get("occurredon"):
        return _day(d["occurredon"])
    if d.get("doctype"):
        return _thing(documents.TITLES.get(d["doctype"], d["doctype"]))
    got = d.get("credentialcode") or d.get("code")
    if got:
        # The house phrasing first, then what the catalog calls it, and only then the code itself.
        return SUBJECT_WORDS.get(got) or (names or {}).get(got) or got.replace("_", " ").title()
    if d.get("employer"):
        return d["employer"].title()
    if d.get("sentto"):
        return d["sentto"]
    if action == "drugtest" and d.get("reason"):
        # The reason's own word, not the code it is stored under. "returntoduty" is how the column
        # spells it; "Return-to-duty" is how everybody else does, and the line is read by people.
        said = eligibility.REASONS.get(d["reason"], d["reason"].replace("_", " "))
        return f"The {said.lower()} drug and alcohol test"
    return None


def _detail_says(action: str, d: dict) -> str | None:
    """What is worth adding under the sentence - never the subject again, and never an id."""
    if not d:
        return None
    if action == "drugtest":
        # The result in its own words too - "negative" is fine, "adulterated" reads as a typo
        # without the vocabulary behind it.
        said = eligibility.RESULTS.get(d.get("result"), d.get("result"))
        return " · ".join(filter(None, [said, d.get("collectedon")]))
    if action in ("order", "file"):
        return " · ".join(filter(None, [d.get("outcome"), d.get("issuedon")]))
    if action == "employer-attempt":
        return d.get("channel")
    if action in ("employer-gfe",):
        return d.get("status")
    if action == "employer-review":
        return d.get("disposition")
    if action == "employment-decision":
        return " · ".join(filter(None, [d.get("decision"), d.get("sapinfogivenon")]))
    if action == "accident":
        return d.get("occurredon")
    if action in ("review", "reviewed"):
        return d.get("finding")
    if action in ("answered-on-request",):
        return d.get("answer")
    return d.get("note")


# What kind of record the line is about, where the log's payload does not say. The entity is always
# recorded; it is the difference between "a record was read" and "the driving record was read", and
# a feed that cannot tell somebody WHICH record is a feed nobody can audit from.
ENTITY_WORDS = {
    "drivermvr": "The driving record",
    "driverreport": "The report",
    "roadtest": "The road test",
    "transitmedical": "The bus transit medical examination",
    "credential": "The document",
    "driverreview": "The annual review",
    "annualreview": "The annual review",
    "employerinquiry": "The previous employer inquiry",
    # `create`, `update`, `delete`, `view` and `open` are used across several kinds of record, so
    # without these the line says what the FIRST caller happened to be about. A licence added to a
    # file printed as "The driver record was created", which is not vague - it is untrue.
    "driver": "The driver record",
    "driverlicense": "The driver's license",
    "driverapplication": "The application",
    "signeddocument": "The signed document",
    "drugtest": "The drug and alcohol test",
    "exclusioncheck": "The exclusion screening",
    "companyquestion": "The company question",
    "vehicle": "The vehicle record",
    "user": "The user account",
    "auditpacket": "The audit packet",
    "auditrequest": "The audit request",
    "importbatch": "The trip import",
}


def _sentence(action: str, d: dict, driver: str, user: str | None,
              entity: str | None = None, names: dict | None = None) -> tuple[str, str]:
    """The whole line, with the person in it, and whose act it was.

    The name belongs IN the sentence rather than under it: a reader scanning a year of history is
    reading sentences, and a column of names underneath makes them join two things up for
    themselves on every row."""
    template, actor = ACTIVITY_WORDS.get(action, (action, "office"))
    named, _, fallback = template.partition("|")
    by = driver if actor == "driver" else (user or "the office")
    subject = _subject(action, d or {}, names) or ENTITY_WORDS.get(entity or "")
    # The conclusion goes in the sentence. It used to sit underneath as a lone word - "qualified" -
    # which made a reader join two things up on every row, and said nothing at all on the rows that
    # had no conclusion to report.
    finding = _words_for(action, d or {})
    line = named if ("{what}" not in named or subject) else fallback
    if "{finding}" in line and not finding:
        line = fallback if "{what}" not in fallback or subject else fallback
        line = line.replace(" and found {finding}", "")
    return line.format(what=subject, by=by, finding=finding or ""), actor


# The registers, by name. "An exclusion screening" is three different obligations wearing one coat.
EXCLUSION_WORDS = {
    "OIG_LEIE": "The OIG LEIE exclusion screening",
    "SAM_EXCLUSIONS": "The SAM.gov exclusion screening",
    "FL_AHCA": "The Florida AHCA exclusion screening",
}

# What barred the driver. 49 CFR 382.501 treats both the same way; a file has to say which it was.
PROHIBITION_WORDS = {
    "clearinghouse": "a Clearinghouse query that came back prohibited",
    "actualknowledge": "actual knowledge of a violation",
}

# What an exclusion screening concluded, in words rather than in the column's spelling.
EXCLUSION_RESULTS = {
    "clear": "clear",
    "potential": "a possible match",
    "confirmed": "a confirmed exclusion",
}


def _day(value) -> str:
    """A date as a reader says it. The log stores them as text, so this takes them as it finds
    them and leaves anything it does not recognise alone rather than guessing."""
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%m/%d/%Y")
    except (TypeError, ValueError):
        return str(value)


def _words_for(action: str, d: dict) -> str | None:
    """A verdict in the words the rest of the application uses for it."""
    if action in ("exclusion-check", "exclusion-settled"):
        got = (d.get("result") or "").strip()
        return EXCLUSION_RESULTS.get(got, got) or None
    if action in ("review", "reviewed"):
        got = (d.get("finding") or d.get("outcome") or "").strip()
        # The word itself, not the sentence the filing form explains it with. "found qualified"
        # reads; "found nothing on the record affects this driver's qualification" does not.
        return got.replace("_", " ").lower() or None
    return None


@router.get("/drivers/{driverid}/application/activity")
def application_activity(driverid: str, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Everything that has happened to this application: what the driver did, what they signed, what
    they uploaded, and what the office has done with it - newest first."""
    acct = user["accountid"]
    driver = _applicant(conn, acct, driverid)
    who = f'{driver["firstname"]} {driver["lastname"]}'.strip().title()
    app_ = row(conn, """
        SELECT recordid, status, startedon, submittedon, data FROM driverapplications
        WHERE driverid = :id AND accountid = :a ORDER BY startedon DESC LIMIT 1
    """, id=driverid, a=acct)
    data = json.loads((app_ or {}).get("data") or "{}")
    events = []

    def entry(at, what, actor, by, detail=None, ip=None):
        """One line of history: what happened, and whose act it was.

        `actor` is the kind of person - the driver, somebody in this office, or an outside party -
        because that is the distinction a reader needs first and the one a name alone does not
        give. `by` is who exactly."""
        return {"at": str(at), "what": what, "actor": actor, "by": by,
                "detail": detail or None, "ip": ip}

    # What each document the driver sent in was asked for. The log is append-only, so a line
    # written before it carried the code cannot be rewritten - it is answered here instead, from
    # the request that produced the document.
    asked_for = {r["documentid"]: r["credentialcode"] for r in rows(conn, """
        SELECT documentid, credentialcode FROM uploadrequests
        WHERE accountid = :a AND driverid = :d AND documentid IS NOT NULL
    """, a=acct, d=driverid)}

    # What the codes in those payloads are called. A log line that says "Prior Violation Rtd" is
    # the code leaking into a document somebody has to read in an audit.
    catalog = {r["code"]: r["name"] for r in rows(conn, """
        SELECT code, name FROM compliancerules
        WHERE subject = 'driver' AND effectiveto IS NULL AND (accountid IS NULL OR accountid = :a)
    """, a=acct)}
    catalog.update({r["code"]: r["name"] for r in rows(conn, """
        SELECT code, name FROM credentialtypes WHERE subject = 'driver'
    """)})
    catalog.update({r["code"]: r["question"] for r in rows(conn, """
        SELECT code, question FROM companyquestions
    """)})

    for r in rows(conn, """
        SELECT l.action, l.entitytype, l.added, l.ip, l.detail, u.name AS username
        FROM activitylog l LEFT JOIN users u ON u.recordid = l.userid
        WHERE l.accountid = :a AND l.entityid = :id
        ORDER BY l.added DESC LIMIT 200
    """, a=acct, id=driverid):
        said = json.loads(r["detail"]) if r["detail"] else None
        if said and not said.get("code") and asked_for.get(said.get("documentid")):
            said = {**said, "code": asked_for[said["documentid"]]}
        sentence, actor = _sentence(r["action"], said or {}, who, r["username"], r["entitytype"],
                                    catalog)
        events.append(entry(r["added"], sentence, actor,
                            who if actor == "driver" else (r["username"] or "The office"),
                            _detail_says(r["action"], said or {}), r["ip"]))

    for doc, sig in signatures.signed(conn, acct, driverid).items():
        events.append(entry(sig["signedon"],
                            f'{_thing(documents.TITLES.get(doc, doc))} was signed by {who}',
                            "driver", who, None, sig["ip"]))

    for kind, up in (data.get("uploads") or {}).items():
        d = row(conn, "SELECT filename, bytes, added FROM documents WHERE recordid = :id",
                id=up.get("documentid"))
        if d:
            events.append(entry(d["added"],
                                f"The {kind.replace('_', ' ')} was uploaded by {who} with their "
                                f"application",
                                "driver", who, d["filename"]))

    # What came back from outside, which the log does not hold: an employer's reply and an
    # examiner's road test are answered by people with no account here.
    for inq in rows(conn, """
        SELECT employer, respondedby, respondedon, respondedip FROM employerinquiries
        WHERE accountid = :a AND driverid = :d AND respondedon IS NOT NULL
    """, a=acct, d=driverid):
        answered = (inq["respondedby"] or inq["employer"] or "A previous employer").title()
        firm = (inq["employer"] or "a previous employer").title()
        events.append(entry(inq["respondedon"],
                            f"The safety performance history request was answered by {answered} "
                            f"at {firm}",
                            "outside", answered, None, inq["respondedip"]))
    for t in rows(conn, """
        SELECT examinername, result, completedon, completedip FROM roadtests
        WHERE accountid = :a AND driverid = :d AND completedon IS NOT NULL
    """, a=acct, d=driverid):
        ended = {"pass": "marked as passed", "fail": "marked as failed"}.get(
            t["result"], "left undecided")
        examiner = (t["examinername"] or "the examiner").title()
        events.append(entry(t["completedon"],
                            f"The road test was completed by {examiner} and {ended}",
                            "outside", examiner, None, t["completedip"]))

    if app_ and app_["submittedon"]:
        events.append(entry(app_["submittedon"], f"The application was submitted by {who}",
                            "driver", who))
    if app_:
        events.append(entry(app_["startedon"], f"The application was started by {who}",
                            "driver", who))
    events.sort(key=lambda e: e["at"], reverse=True)
    return {"status": (app_ or {}).get("status"), "events": events}


class DecisionIn(BaseModel):
    action: str                          # pending | decline | corrections
    note: str | None = None


# What each decision does to the driver and to their application.
DECISIONS = {
    "pending": ("pending", "submitted", "driverapplication-pending"),
    "decline": ("declined", "rejected", "driverapplication-declined"),
    "corrections": ("appcor", "started", "driverapplication-returned"),
}


@router.post("/drivers/{driverid}/application/decision")
def decide_application(driverid: str, body: DecisionIn, request: Request, tasks: BackgroundTasks,
                       user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Move an application on: into review, out of the running, or back to the driver to correct."""
    if body.action not in DECISIONS:
        raise HTTPException(400, "Unknown action")
    driver = row(conn, """
        SELECT recordid, status FROM drivers WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=driverid, a=user["accountid"])
    if not driver:
        raise HTTPException(404, "Driver not found")
    app_ = row(conn, """
        SELECT recordid, data FROM driverapplications WHERE driverid = :id AND accountid = :a
        ORDER BY startedon DESC LIMIT 1
    """, id=driverid, a=user["accountid"])
    if not app_:
        raise HTTPException(404, "This driver has no online application")
    if driver["status"] in ("hired", "inactive"):
        raise HTTPException(409, "This driver is already on the roster")

    driverstatus, appstatus, action = DECISIONS[body.action]
    note = (body.note or "").strip()
    data = json.loads(app_["data"] or "{}")
    data.setdefault("review", []).append({
        "action": body.action, "note": note or None, "by": user["recordid"], "on": str(utcnow()),
    })
    run(conn, "UPDATE drivers SET status = :s, updated = :now WHERE recordid = :id",
        s=driverstatus, now=utcnow(), id=driverid)
    run(conn, """
        UPDATE driverapplications SET status = :s, data = :d, reviewedby = :u, reviewedon = :now,
                                      submittedon = CASE WHEN :s = 'started' THEN NULL ELSE submittedon END
        WHERE recordid = :id
    """, s=appstatus, d=json.dumps(data), u=user["recordid"], now=utcnow(), id=app_["recordid"])
    log(conn, user, action, "driver", driverid, {"note": note} if note else None, ip=client_ip(request))
    # Sent back means the driver has something to do, so they are told what and given the way back in.
    if body.action == "corrections":
        who = row(conn, """
            SELECT d.firstname, d.lastname, d.email, a.name AS accountname, a.accountnumber
            FROM drivers d JOIN accounts a ON a.recordid = d.accountid WHERE d.recordid = :id
        """, id=driverid)
        if who and who["email"]:
            tasks.add_task(
                _tell_driver_to_correct, email=who["email"],
                name=f"{who['firstname']} {who['lastname']}".strip(), accountname=who["accountname"],
                link=f"{settings.public_url.rstrip('/')}/account/{who['accountnumber']}/apply",
                note=note or None)
    saved(conn)
    return {"ok": True, "status": driverstatus}


# ------------------------------------------------------------------------------------------------
# The hiring file - screenings ordered, documents collected, and the decision at the end of it
# ------------------------------------------------------------------------------------------------

def _applicant(conn: Connection, accountid: str, driverid: str) -> dict:
    driver = row(conn, """
        SELECT recordid, firstname, lastname, status, drivernumber, hiredon, email, dob,
               -- Whether Chapter 14-90 reaches this driver, which decides what goes in the
               -- packet they are sent on hire.
               chapter1490
        FROM drivers WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=driverid, a=accountid)
    if not driver:
        raise HTTPException(404, "Driver not found")
    return driver


@router.get("/company/questions")
def company_questions(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """What decides which rules reach this company's drivers, and what it has answered.

    An unanswered question is not a 'no'. It is reported as unanswered, and every rule that needs
    it says so rather than quietly deciding."""
    return {"questions": factset.questions(conn, user["accountid"])}


class AnswerIn(BaseModel):
    answer: bool | None = None


@router.put("/company/questions/{code}")
def answer_question(code: str, body: AnswerIn, request: Request,
                    user: dict = Depends(account_admin), conn: Connection = Depends(get_conn)):
    if not row(conn, "SELECT 1 AS x FROM companyquestions WHERE code = :c AND active = 1", c=code):
        raise HTTPException(404, "Unknown question")
    run(conn, """
        INSERT INTO companyanswers (accountid, code, answer, updated, updatedby)
        VALUES (:a, :c, :ans, :now, :u)
        ON DUPLICATE KEY UPDATE answer = VALUES(answer), updated = VALUES(updated),
                                updatedby = VALUES(updatedby)
    """, a=user["accountid"], c=code, ans=None if body.answer is None else int(body.answer),
        now=utcnow(), u=user["recordid"])
    log(conn, user, "answer", "companyquestion", code, {"code": code, "answer": body.answer},
        ip=client_ip(request))
    out = factset.questions(conn, user["accountid"])
    saved(conn)
    return {"questions": out}


# ------------------------------------------------------------------------------------------------
# Exclusion screening: what the office does by hand, beside what the monthly job does on its own.
#
# The job screens everybody against the published list and writes the clean results too - see
# app/screening.py. These two are for the parts a machine cannot do: recording a check somebody ran
# on OIG's own site, and settling a possible match against the SSN, which is the only definitive
# answer and exists nowhere but their form.
# ------------------------------------------------------------------------------------------------

EXCLUSION_SOURCES = ("OIG_LEIE", "SAM_EXCLUSIONS", "FL_AHCA")


@router.post("/drivers/{driverid}/exclusion-checks")
async def record_exclusion_check(
    driverid: str,
    request: Request,
    source: str = Form("OIG_LEIE"),
    checkedon: date = Form(...),
    namessearched: str = Form(...),
    result: str = Form(...),                 # clear | potential | confirmed
    note: str | None = Form(None),
    performedby: str = Form("tripproof"),
    file: UploadFile | None = File(None),
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    """A check somebody ran themselves, on OIG's site or a vendor's."""
    acct = user["accountid"]
    driver = _applicant(conn, acct, driverid)
    if source not in EXCLUSION_SOURCES:
        raise HTTPException(400, "Unknown list")
    if result not in ("clear", "potential", "confirmed"):
        raise HTTPException(400, "Unknown result")
    if not namessearched.strip():
        raise HTTPException(400, "Say which names were searched")

    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    # Recorded for today means recorded now. Storing it at midnight would put it behind the
    # morning's automated run, so the older answer would read as the current one.
    when = utcnow() if checkedon == date.today() else datetime.combine(checkedon, time(12, 0))
    run(conn, """
        INSERT INTO exclusionchecks (recordid, accountid, driverid, source, checkedon, namessearched,
                                     dobsearched, result, evidencedocid, note, performedby)
        VALUES (:id, :a, :d, :src, :on, :names, :dob, :res, :doc, :n, :by)
    """, id=(checkid := newid()), a=acct, d=driverid, src=source, on=when,
        names=namessearched.strip().upper()[:512], dob=driver.get("dob"), res=result, doc=documentid,
        n=(note or "").strip()[:512] or None, by=performedby[:32])
    _filed_here(conn, acct, driverid, "exclusionchecks", checkid, user["recordid"])
    log(conn, user, "exclusion-check", "driver", driverid, {"source": source, "result": result},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/drivers/{driverid}/exclusion-checks/{checkid}/settle")
async def settle_exclusion_check(
    driverid: str,
    checkid: str,
    request: Request,
    result: str = Form(...),                 # clear | confirmed
    verifymethod: str = Form("ssn"),
    note: str | None = Form(None),
    file: UploadFile = File(...),            # required: OIG asks for the screen-shot by name
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    """Settle a possible match, against the SSN, on OIG's form.

    The screenshot is required rather than encouraged. OIG's 2013 bulletin asks providers to
    "maintain documentation of the initial name search performed (such as a printed screen-shot…)
    and any additional searches conducted, in order to verify results of potential name matches" -
    and a match settled with nothing behind it is worse than one left open, because it looks
    answered."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    if result not in ("clear", "confirmed"):
        raise HTTPException(400, "A possible match is either this person or it is not")
    held = row(conn, """
        SELECT recordid, source, result FROM exclusionchecks
        WHERE recordid = :c AND accountid = :a AND driverid = :d
    """, c=checkid, a=acct, d=driverid)
    if not held:
        raise HTTPException(404, "No such screening")
    if not file.filename:
        raise HTTPException(400, "Attach the screenshot of the verification")

    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "That file is larger than 20 MB")
    documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                              user["recordid"], origin=storage.OFFICE)
    run(conn, """
        UPDATE exclusionchecks SET result = :res, verifiedby = :u, verifiedon = :now,
               verifymethod = :how, evidencedocid = :doc, note = COALESCE(:n, note)
        WHERE recordid = :c
    """, res=result, u=user["recordid"], now=utcnow(), how=verifymethod[:24], doc=documentid,
        n=(note or "").strip()[:512] or None, c=checkid)
    log(conn, user, "exclusion-settled", "driver", driverid,
        {"source": held["source"], "result": result}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/drivers/{driverid}/exclusion-checks/{checkid}/reinstate")
async def reinstate_driver(
    driverid: str,
    checkid: str,
    request: Request,
    liftedon: date = Form(...),
    reason: str = Form(...),
    file: UploadFile = File(...),        # OIG issues a written notice; nothing else lifts this
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    """Lift a confirmed exclusion, against OIG's written notice of reinstatement.

    An exclusion does not lapse - the person has to apply and be granted reinstatement - so there is
    always a document, and requiring it is what separates a reinstatement from somebody deciding the
    red mark should go away. The confirmed row is marked rather than replaced: what the file held on
    the day a trip ran is the question that gets asked afterwards."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    held = row(conn, """
        SELECT recordid, result, source, liftedon FROM exclusionchecks
        WHERE recordid = :c AND accountid = :a AND driverid = :d
    """, c=checkid, a=acct, d=driverid)
    if not held:
        raise HTTPException(404, "No such screening")
    if held["result"] != "confirmed":
        raise HTTPException(409, "Only a confirmed exclusion can be lifted")
    if held["liftedon"]:
        raise HTTPException(409, "That exclusion has already been lifted")
    if not file.filename:
        raise HTTPException(400, "Attach the notice of reinstatement")
    if not reason.strip():
        raise HTTPException(400, "Say what lifted it")

    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "That file is larger than 20 MB")
    documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                              user["recordid"], origin=storage.OFFICE)
    run(conn, """
        UPDATE exclusionchecks SET liftedon = :on, liftedby = :u, liftreason = :why, liftdocid = :doc
        WHERE recordid = :c
    """, on=liftedon, u=user["recordid"], why=reason.strip()[:512], doc=documentid, c=checkid)

    # And a screening row of its own, dated the reinstatement, so the history reads forwards rather
    # than leaving the driver's current standing to be inferred from an absence.
    run(conn, """
        INSERT INTO exclusionchecks (recordid, accountid, driverid, source, checkedon, namessearched,
                                     result, evidencedocid, note, performedby)
        SELECT :id, :a, :d, source, :now, namessearched, 'clear', :doc, :note, 'tripproof'
        FROM exclusionchecks WHERE recordid = :c
    """, id=newid(), a=acct, d=driverid, now=datetime.combine(liftedon, time(12, 0)), doc=documentid,
        note=f"Reinstated - {reason.strip()}"[:512], c=checkid)
    log(conn, user, "exclusion-reinstated", "driver", driverid,
        {"source": held["source"], "liftedon": str(liftedon), "reason": reason.strip()},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/drivers/{driverid}/requirements/{code}/document")
async def file_against_requirement(
    driverid: str,
    code: str,
    request: Request,
    effectiveon: date = Form(...),
    note: str | None = Form(None),
    file: UploadFile = File(...),
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    """File a document straight against a requirement.

    For everything TripProof does not produce itself: a DOT application signed on paper, a form
    filled in before the company used this, a copy sent over by a previous employer. It answers the
    rule exactly as well as a record the application generated - a file is not less compliant for
    having arrived by scanner - and it is the fallback for every requirement rather than a special
    case for one."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    rule = row(conn, "SELECT recordid, name, reviewrequired FROM compliancerules "
                     "WHERE code = :c AND subject = 'driver' AND effectiveto IS NULL "
                     "AND (accountid IS NULL OR accountid = :a) LIMIT 1", c=code, a=acct)
    if not rule:
        raise HTTPException(404, "No such requirement")
    if not file.filename:
        raise HTTPException(400, "Choose a file")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "That file is larger than 20 MB")
    documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                              user["recordid"], origin=storage.OFFICE)
    # Filing one IS reading one. Where the rule asks for a reading - the prior-violation
    # verification does, because the applicant's own account of it does not close it - the act of
    # somebody in the office putting the paperwork on the file is that reading, and is recorded as
    # such rather than leaving the requirement waiting for a second person to agree.
    run(conn, """
        INSERT INTO complianceevidence (recordid, accountid, ruleid, subject, subjectid, sourcetable,
                                        sourceid, effectiveon, determination, note)
        VALUES (:id, :a, :r, 'driver', :d, 'documents', :doc, :on, :det, :n)
    """, id=newid(), a=acct, r=rule["recordid"], d=driverid, doc=documentid, on=effectiveon,
        det=("reviewed" if rule["reviewrequired"] else None),
        n=(note or "").strip()[:512] or None)
    log(conn, user, "requirement-document", "driver", driverid, {"code": code}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class VerifyIn(BaseModel):
    documentid: str
    note: str | None = None


@router.post("/drivers/{driverid}/requirements/{code}/verified")
def verify_requirement(driverid: str, code: str, body: VerifyIn, request: Request,
                       user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Somebody in the office has read a document already on file and says it answers this rule.

    The difference from filing one: the paper is already here. A driver who disclosed a prior
    violation sent their SAP paperwork in with the questionnaire, bound into that one document, and
    asking the office to upload a second copy of a file they are looking at would be asking them to
    make a duplicate to prove they read the original."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    rule = row(conn, "SELECT recordid, name FROM compliancerules "
                     "WHERE code = :c AND subject = 'driver' AND effectiveto IS NULL "
                     "AND (accountid IS NULL OR accountid = :a) LIMIT 1", c=code, a=acct)
    if not rule:
        raise HTTPException(404, "No such requirement")
    doc = row(conn, "SELECT recordid FROM documents WHERE recordid = :i AND accountid = :a "
                    "AND deleted IS NULL", i=body.documentid, a=acct)
    if not doc:
        raise HTTPException(404, "No such document")
    run(conn, """
        INSERT INTO complianceevidence (recordid, accountid, ruleid, subject, subjectid, sourcetable,
                                        sourceid, effectiveon, determination, note)
        VALUES (:id, :a, :r, 'driver', :d, 'documents', :doc, :on, 'reviewed', :n)
    """, id=newid(), a=acct, r=rule["recordid"], d=driverid, doc=body.documentid,
        on=localnow(user["timezone"]).date(), n=(body.note or "").strip()[:512] or None)
    log(conn, user, "requirement-verified", "driver", driverid,
        {"code": code, "documentid": body.documentid}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "evaluation": evaluation}


class ReadIn(BaseModel):
    sourcetable: str
    sourceid: str
    code: str | None = None          # the requirement this reading answers, so its alert clears too
    note: str | None = None


# Every table an evidence record can live in. Named rather than taken from the request, so this
# cannot be pointed at anything else in the database.
def _with_readings(conn: Connection, acct: str, driverid: str, rule: dict,
                   records: list[dict]) -> list[dict]:
    """Each record, with whether this office still has to read it.

    Asked of the engine rather than worked out again here, so the eye on the requirements list and
    the button inside the dialog are answering the same question. Without this the screen offered a
    reading only where the document arrived down an upload link, and a licence photographed on the
    application sat in review with nowhere to review it."""
    read = rules.already_read(conn, acct, driverid)
    readdocs = rules.read_documents(conn, acct, driverid)
    return [{**r, "needsreading": rules.needs_reading(rule, r, read, readdocs)} for r in records]


READABLE = ("credentials", "drivermvrs", "driverreports", "roadtests", "drugtests",
            "transitmedicals", "documentsignatures", "exclusionchecks", "driverlicenses",
            "employerinquiries", "documents")


@router.post("/drivers/{driverid}/evidence/read")
def mark_evidence_read(driverid: str, body: ReadIn, request: Request,
                       user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Somebody in this office has read one record and says so.

    One act, one place. A reading is the same thing whether what was read is a laboratory result, a
    medical certificate, a licence copy or a federal database answer - and a flag per kind of
    record is how one kind ends up without one."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    if body.sourcetable not in READABLE:
        raise HTTPException(400, "That is not an evidence record")
    run(conn, """
        INSERT INTO documentreads (recordid, accountid, subject, subjectid, sourcetable, sourceid,
                                   readby, note)
        VALUES (:id, :a, 'driver', :d, :t, :s, :u, :n)
        ON DUPLICATE KEY UPDATE readon = CURRENT_TIMESTAMP, readby = VALUES(readby)
    """, id=newid(), a=acct, d=driverid, t=body.sourcetable, s=body.sourceid,
        u=user["recordid"], n=(body.note or "").strip()[:512] or None)
    # Read means read: it comes out of the inbox at the same moment it goes green, for the same
    # reason the three went in together.
    events.read_arrivals(conn, acct, "driver", driverid, body.code)
    log(conn, user, "evidence-read", "driver", driverid,
        {"sourcetable": body.sourcetable, "sourceid": body.sourceid}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "evaluation": evaluation}


# ------------------------------------------------------------------------------------------------
# What this company asks on top of what the law asks
#
# Kept apart from the company's ANSWERS, which live on the same settings page and are a different
# kind of thing. An answer is a fact about the company - are you HIPAA covered, do you carry
# Medicaid trips - and it changes what the law requires. An election is a choice, and it changes
# what this company requires. Running them through one mechanism is how a company ends up saying
# something untrue about itself in order to switch on a requirement it merely wants.
# ------------------------------------------------------------------------------------------------

# Who a company asks a requirement of, beyond whoever the regulation reaches. "off" is kept for
# the elections already recorded under it and means the same as "regulation".
ADOPTIONS = ("regulation", "alldrivers", "cdl", "noncdl", "off")


class PolicyIn(BaseModel):
    applyto: str
    reason: str | None = None


def _policy_context(conn: Connection, acct: str, code: str | None = None) -> dict:
    """Everything a company policy fills itself in from.

    The named people come from their appointments rather than from anything typed into the policy,
    which is the whole point: appoint somebody else and the next copy names them, with no document
    to go and edit. Blanks left where nothing is on file - a policy that invents a DER would be
    worse than one that shows it has none."""
    a = row(conn, "SELECT name, address1, address2, city, state, zip, phone, usdot, "
                  "dapolicydiscipline, dapolicyother FROM accounts WHERE recordid = :a",
            a=acct) or {}
    # This policy's own effective date. A document prints the day IT took effect, never the day
    # another one did.
    took = (row(conn, "SELECT effectiveon FROM companypolicies WHERE accountid = :a AND code = :c",
                a=acct, c=code) or {}).get("effectiveon") if code else None

    def holder(role: str) -> dict:
        return row(conn, """
            SELECT u.name, u.email, u.role
            FROM companyroles r JOIN users u ON u.recordid = r.userid
            WHERE r.accountid = :a AND r.role = :role AND r.until IS NULL AND u.deleted IS NULL
            ORDER BY r.since DESC LIMIT 1
        """, a=acct, role=role) or {}

    def line(who: dict) -> str:
        return f'{who["name"]} ({who["email"]})' if who.get("name") else "__________"

    der, safety = holder("der"), holder("safety")
    security, bbpadmin = holder("security"), holder("bbpadmin")
    choice = a.get("dapolicydiscipline")
    said = (a.get("dapolicyother") if choice == "other"
            else documents.DISCIPLINE.get(choice))
    street = ", ".join(x for x in (a.get("address1"), a.get("address2")) if x)
    town = " ".join(x for x in (a.get("city"), a.get("state"), a.get("zip")) if x)
    return {
        "company": a.get("name") or "",
        "address": ", ".join(x for x in (street, town) if x) or "__________",
        "telephone": a.get("phone") or "__________",
        # Blank rather than invented. A policy that prints a USDOT number the carrier does not
        # hold is a policy that misstates who it is.
        "usdot": (a.get("usdot") or "").strip() or "__________",
        "effectivedate": took.strftime("%d %B %Y") if took else "__________",
        "dername": der.get("name") or "__________",
        "dertitle": (der.get("role") or "").title() or "__________",
        "derphone": a.get("phone") or "__________",
        "deremail": der.get("email") or "__________",
        "derline": line(der),
        # The SSPP's own named person. Chapter 14-90 wants the plan to say who administers it, and
        # the answer is an appointment here rather than a name typed into twenty pages of prose.
        "safetyname": safety.get("name") or "__________",
        "safetytitle": (safety.get("role") or "").title() or "__________",
        "safetyphone": a.get("phone") or "__________",
        "safetyemail": safety.get("email") or "__________",
        "safetyline": line(safety),
        # 45 CFR 164.308(a)(2) and 29 CFR 1910.1030(c)(1) both want a named person, and both
        # policies print one. From the appointment on file, never from anything typed into
        # the words: appoint somebody else and the next copy names them.
        "securityname": security.get("name") or "__________",
        "securitytitle": (security.get("role") or "").title() or "__________",
        "securityphone": a.get("phone") or "__________",
        "securityemail": security.get("email") or "__________",
        "securityline": line(security),
        "bbpname": bbpadmin.get("name") or "__________",
        "bbptitle": (bbpadmin.get("role") or "").title() or "__________",
        "bbpphone": a.get("phone") or "__________",
        "bbpemail": bbpadmin.get("email") or "__________",
        "bbpline": line(bbpadmin),
        "discipline": said or "[The company has not chosen its policy on this. Set it on Company "
                              "Requirements.]",
        # The supervisor training record is a published sheet like the others, but every line
        # about a person is filled in by that person when they sign their own copy. Read as a
        # policy - the blank form, the wording editor - those lines are rules on a page.
        **_supervisor_blanks({}),
    }


# ------------------------------------------------------------------------------------------------
# What one supervisor's copy of the training record says - 49 CFR 382.603.
#
# One function because there is one set of blanks. The policy view rules them; the supervisor
# signing fills them. Two lists would be two lists free to disagree about what the form asks.
# ------------------------------------------------------------------------------------------------

SUPERVISOR_BLANK = "____________________"

# The drawn signature in a stored record, so the stamp can be put under it when it is read.
SIGNATURE_DRAWN = re.compile(r'<img\b[^>]*vertical-align:middle[^>]*>')


def _with_stamp(html: str, said: dict) -> str:
    """The audit stamp under the signature, drawn when the record is READ.

    Everything that proves the signing - who signed, which signature on file it was, and when
    and from where it was used - already lives on the signature row. Baking a copy of it into
    the words at signing time would be a second copy of one fact, and would leave every record
    signed before that change with nothing under its signature. So the words stay frozen, as
    they must, and the stamp is drawn beside them from the row that is the authority for it.
    """
    stamp = " · ".join(x for x in (
        "Signed electronically", said.get("signername") or said.get("typedname"),
        said.get("signatureid") or said.get("recordid"),
        f'{said["signedon"]:%Y-%m-%d %H:%M:%S} UTC' if said.get("signedon") else None,
        f'IP {said.get("ip") or "not recorded"}') if x)
    return SIGNATURE_DRAWN.sub(
        lambda m: f'{m.group(0)}<br><span class="small muted">{escape(stamp)}</span>',
        html or "", count=1)


def _supervisor_blanks(held: dict) -> dict:
    return {
        "supervisor": held.get("supervisor") or SUPERVISOR_BLANK,
        "supervisortitle": (held.get("supervisortitle") or "").title() or SUPERVISOR_BLANK,
        "designated": (f'{held["designated"]:%m/%d/%Y}' if held.get("designated")
                       else SUPERVISOR_BLANK),
        "provider": held.get("provider") or SUPERVISOR_BLANK,
        "alcoholminutes": (held["alcoholminutes"]
                           if held.get("alcoholminutes") is not None else "____"),
        "drugminutes": (held["drugminutes"]
                        if held.get("drugminutes") is not None else "____"),
        "completedon": (f'{held["completedon"]:%m/%d/%Y}' if held.get("completedon")
                        else SUPERVISOR_BLANK),
        # Section 7 is the company's own verification, and the company verifies it on paper.
        # Nothing in here types a name onto a line somebody else has to stand behind.
        "verifiedby": SUPERVISOR_BLANK,
        # Blank where nobody has said either way, rather than "No": the answer is only No once
        # a supervisor has filled the form in and attached nothing.
        "certificate": (("Yes" if held.get("documentid") else "No")
                        if held.get("completedon") else SUPERVISOR_BLANK),
        "note": held.get("note") or SUPERVISOR_BLANK,
        # Filled once the supervisor has signed, because that is what the form is for -
        # section 6 is their acknowledgment, and a record that shows it blank beside a
        # signature already on file is showing the wrong thing.
        "supervisorsignature": SUPERVISOR_BLANK,
        "supervisorsignedon": SUPERVISOR_BLANK,
    }


@router.get("/company/policies/{code}")
def company_policy(code: str, user: dict = Depends(current_user),
                   conn: Connection = Depends(get_conn)):
    """One of this company's policies, filled in and ready to read, print or hand to a driver."""
    acct = user["accountid"]
    try:
        doc = documents.company_policy(code)
    except KeyError:
        raise HTTPException(404, "No such policy") from None
    a = row(conn, "SELECT dapolicydiscipline, dapolicyother FROM accounts WHERE recordid = :a",
            a=acct) or {}
    # Theirs if they have edited it, ours otherwise. The merge fields fill either way, so a company
    # that rewrote half the policy still gets the DER from the appointment on file.
    mine = row(conn, """
        SELECT text, basedon, updated, effectiveon FROM companypolicies
        WHERE accountid = :a AND code = :c
    """, a=acct, c=code) or {}
    source = mine.get("text") or doc["text"]
    return {**doc, "text": documents.fill_exact(source, _policy_context(conn, acct, code)),
            # The words before filling, which is what an editor has to edit.
            "source": source, "published": doc["text"],
            "own": bool(mine.get("text")), "basedon": mine.get("basedon"),
            "editedon": mine.get("updated"),
            "effectiveon": mine.get("effectiveon"),
            "discipline": a.get("dapolicydiscipline"),
            "disciplineother": a.get("dapolicyother"),
            "choices": {**documents.DISCIPLINE, "other": "Something else"}}


# Declared BEFORE the routes that take a policy code. FastAPI matches in declaration order, and
# "/company/policies/settings" is a perfectly good match for "/company/policies/{code}" - which is
# how saving the effective date came back asking for the text of a policy called "settings".
class PolicySettingsIn(BaseModel):
    code: str
    effectiveon: date | None = None
    discipline: str | None = None
    other: str | None = None


@router.put("/company/policies/settings")
def set_policy_settings(body: PolicySettingsIn, request: Request,
                        user: dict = Depends(account_admin),
                        conn: Connection = Depends(get_conn)):
    """Adopt one policy, on the day this company says it took effect.

    The date is the adoption and the adoption is what the requirement reads: four policies are four
    documents, taking effect on four days, so the date is kept against the policy rather than
    against the account."""
    acct = user["accountid"]
    if body.code not in documents.COMPANY_POLICIES:
        raise HTTPException(404, "No such policy")
    if body.discipline and body.discipline not in (*documents.DISCIPLINE, "other"):
        raise HTTPException(400, "Unknown choice")
    if body.discipline == "other" and not (body.other or "").strip():
        raise HTTPException(400, "Say what the policy is")
    run(conn, """
        INSERT INTO companypolicies (accountid, code, effectiveon, adoptedby, adoptedon)
        VALUES (:a, :c, :on, :u, :now)
        ON DUPLICATE KEY UPDATE effectiveon = VALUES(effectiveon),
                                adoptedby   = VALUES(adoptedby),
                                adoptedon   = COALESCE(companypolicies.adoptedon, VALUES(adoptedon))
    """, a=acct, c=body.code, on=body.effectiveon, u=user["recordid"], now=utcnow())
    # Section 10 of the DOT policy is a choice about the company, not about one document, so it
    # stays on the account where the rest of the company's own answers live.
    if body.code == "DRUG_POLICY":
        run(conn, """
            UPDATE accounts SET dapolicydiscipline = :d, dapolicyother = :o WHERE recordid = :a
        """, d=body.discipline or None, o=(body.other or "").strip()[:300] or None, a=acct)
    log(conn, user, "policy-settings", "company", acct,
        {"code": body.code, "discipline": body.discipline}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class PolicyTextIn(BaseModel):
    text: str


@router.put("/company/policies/{code}")
def edit_company_policy(code: str, body: PolicyTextIn, request: Request,
                        user: dict = Depends(account_admin),
                        conn: Connection = Depends(get_conn)):
    """Replace the published policy with this company's own wording.

    The merge fields are left alone deliberately: whatever else somebody rewrites, {company} and
    the DER blanks still fill from the record, so the one part that goes stale by hand cannot."""
    acct = user["accountid"]
    try:
        doc = documents.company_policy(code)
    except KeyError:
        raise HTTPException(404, "No such policy") from None
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "The policy cannot be empty")
    run(conn, """
        INSERT INTO companypolicies (accountid, code, text, basedon, updatedby)
        VALUES (:a, :c, :t, :v, :u)
        ON DUPLICATE KEY UPDATE text = VALUES(text), basedon = VALUES(basedon),
                                updated = CURRENT_TIMESTAMP, updatedby = VALUES(updatedby)
    """, a=acct, c=code, t=text, v=doc["version"], u=user["recordid"])
    log(conn, user, "policy-edited", "company", acct, {"code": code}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.delete("/company/policies/{code}")
def revert_company_policy(code: str, request: Request, user: dict = Depends(account_admin),
                          conn: Connection = Depends(get_conn)):
    """Put the published text back, and start tracking our updates again."""
    acct = user["accountid"]
    # Only the words go back. The adoption is a separate act and survives it - a company that
    # puts our wording back has not stopped having a policy.
    run(conn, """
        UPDATE companypolicies SET text = NULL, basedon = NULL, updated = CURRENT_TIMESTAMP
        WHERE accountid = :a AND code = :c
    """, a=acct, c=code)
    run(conn, """
        DELETE FROM companypolicies
        WHERE accountid = :a AND code = :c AND text IS NULL AND effectiveon IS NULL
    """, a=acct, c=code)
    log(conn, user, "policy-reverted", "company", acct, {"code": code}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


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
    return {"trips": rows(conn, """
        SELECT t.recordid, t.externalid, t.tripdate, t.servicelevel, t.billingstatus,
               GROUP_CONCAT(DISTINCT COALESCE(v.externalid, v.vin) SEPARATOR ', ') AS vehicles,
               MIN(l.pickupat) AS startedat, MAX(l.dropoffat) AS finishedat,
               COUNT(l.recordid) AS legs
        FROM triplegs l
          JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
          LEFT JOIN vehicles v ON v.recordid = l.vehicleid AND v.deleted IS NULL
        WHERE l.accountid = :a AND l.driverid = :d
        GROUP BY t.recordid, t.externalid, t.tripdate, t.servicelevel, t.billingstatus
        ORDER BY t.tripdate DESC, t.externalid DESC
        LIMIT 100
    """, a=acct, d=driverid)}


# ------------------------------------------------------------------------------------------------
# Background screening, ordered from Certn
# ------------------------------------------------------------------------------------------------

class ScreeningIn(BaseModel):
    tier: str


@router.get("/drivers/{driverid}/background")
def background_screening(driverid: str, user: dict = Depends(current_user),
                         conn: Connection = Depends(get_conn)):
    """What has been ordered for this driver, and what can be."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    return {
        "available": certn.configured(),
        "tiers": [{"code": k, **{x: v[x] for x in ("name", "price", "covers")}}
                  for k, v in certn.TIERS.items()],
        "orders": rows(conn, """
            SELECT r.recordid, r.tier, r.vendor, r.vendorstatus, r.chargecents, r.orderedon,
                   r.receivedon, r.issuedon, r.outcome, r.reviewstate, r.documentid, r.note,
                   u.name AS orderedbyname
            FROM driverreports r LEFT JOIN users u ON u.recordid = r.orderedby
            WHERE r.accountid = :a AND r.driverid = :d AND r.code = 'BACKGROUND_SCREENING'
            ORDER BY r.createdon DESC
        """, a=acct, d=driverid),
    }


@router.post("/drivers/{driverid}/background/order")
def order_background_screening(driverid: str, body: ScreeningIn, request: Request,
                               user: dict = Depends(editor),
                               conn: Connection = Depends(get_conn)):
    """Order one screening from Certn and put its cost on this account's next invoice.

    The order goes to Certn FIRST and nothing is written here until they hand back a reference. An
    order we cannot name is an order whose result can never be matched to a driver, and a row
    written before the call would be exactly that if the call then failed.

    TripProof pays Certn now and recovers it later, so no card is touched: the charge is a line on
    the next monthly invoice. If recording the charge fails the screening still stands - a driver's
    file is not held up by our billing."""
    acct = user["accountid"]
    driver = _applicant(conn, acct, driverid)
    if body.tier not in certn.TIERS:
        raise HTTPException(400, "Choose a Core or a Complete background check")
    if not driver.get("dob"):
        raise HTTPException(409, "Certn needs this driver's date of birth. Record it first.")
    open_already = row(conn, """
        SELECT recordid FROM driverreports
        WHERE accountid = :a AND driverid = :d AND code = 'BACKGROUND_SCREENING'
          AND receivedon IS NULL AND cancelledon IS NULL
    """, a=acct, d=driverid) if _has_cancelled() else row(conn, """
        SELECT recordid FROM driverreports
        WHERE accountid = :a AND driverid = :d AND code = 'BACKGROUND_SCREENING'
          AND receivedon IS NULL
    """, a=acct, d=driverid)
    if open_already:
        raise HTTPException(409, "A screening is already running for this driver")

    tier = certn.TIERS[body.tier]
    try:
        placed = certn.order(body.tier, driver, driver.get("email"))
    except certn.CertnError as e:
        raise HTTPException(502, str(e)) from e

    reportid = newid()
    run(conn, """
        INSERT INTO driverreports (recordid, accountid, driverid, code, tier, vendor, vendorref,
                                   vendorstatus, chargecents, orderedon, orderedby, lastsyncedon)
        VALUES (:id, :a, :d, 'BACKGROUND_SCREENING', :t, 'certn', :ref, :st, :cents,
                :now, :by, :now)
    """, id=reportid, a=acct, d=driverid, t=body.tier, ref=placed["ref"],
        st=placed["status"], cents=tier["price"], now=utcnow(), by=user["recordid"])

    # The charge, on the next invoice rather than on a card. A failure here is logged and does not
    # undo the screening: the driver's file matters more than the line item, and an order already
    # placed at Certn cannot be unplaced.
    customer = (row(conn, "SELECT stripecustomerid FROM accounts WHERE recordid = :a", a=acct)
                or {}).get("stripecustomerid")
    try:
        billing.charge_next_invoice(
            customer, tier["price"],
            f'{tier["name"]} - {driver["firstname"]} {driver["lastname"]}'.strip(), acct)
    except Exception as e:                                        # noqa: BLE001 - never fatal here
        log_render = logging.getLogger("tripproof.vault")
        log_render.warning("screening ordered but not billed for %s: %s", acct, e)

    log(conn, user, "order", "driverreport", driverid,
        {"code": "BACKGROUND_SCREENING", "tier": body.tier, "cents": tier["price"]},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True, "recordid": reportid}


def _has_cancelled() -> bool:
    """Older installations have no `cancelledon` on this table."""
    return False


@router.post("/drivers/{driverid}/background/{recordid}/refresh")
def refresh_background_screening(driverid: str, recordid: str, request: Request,
                                 user: dict = Depends(editor),
                                 conn: Connection = Depends(get_conn)):
    """Ask Certn where an order has got to, for an office that does not want to wait for a webhook.

    The webhook is how a result normally arrives. This exists because a webhook can be missed, and
    an office with a driver waiting should never be stuck because of it."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    held = row(conn, """
        SELECT recordid, vendorref, vendorstatus FROM driverreports
        WHERE recordid = :id AND accountid = :a AND driverid = :d
    """, id=recordid, a=acct, d=driverid)
    if not held or not held["vendorref"]:
        raise HTTPException(404, "No such order")
    try:
        got = certn.fetch(held["vendorref"])
    except certn.CertnError as e:
        raise HTTPException(502, str(e)) from e
    _land_screening(conn, acct, driverid, held["recordid"], held["vendorref"], got["status"])
    log(conn, user, "order", "driverreport", driverid,
        {"code": "BACKGROUND_SCREENING", "checked": got["status"]}, ip=client_ip(request))
    saved(conn)
    return {"ok": True, "status": got["status"]}


def _land_screening(conn: Connection, acct: str, driverid: str, recordid: str, ref: str,
                    status: str) -> None:
    """Bring one finished screening onto the driver's file.

    The result is NOT a determination. Certn says what it found; whether that disqualifies anybody
    is the company's judgement, so this files the report and leaves it needing to be read - the
    same as every other thing that arrives from outside."""
    if status == "running":
        run(conn, "UPDATE driverreports SET vendorstatus = 'running', lastsyncedon = :now "
                  "WHERE recordid = :id", now=utcnow(), id=recordid)
        return
    documentid = None
    if status == "finished":
        try:
            pdf = certn.report_pdf(ref)
            documentid = storage.keep(conn, acct, "documents", pdf,
                                      f"background-screening-{ref}.pdf", "application/pdf", None, origin=storage.SERVICE)
        except (certn.CertnError, Exception) as e:                # noqa: BLE001
            logging.getLogger("tripproof.vault").warning("report not stored for %s: %s", ref, e)
    run(conn, """
        UPDATE driverreports
           SET vendorstatus = :st, receivedon = :now, issuedon = COALESCE(issuedon, CURRENT_DATE),
               documentid = COALESCE(:doc, documentid), lastsyncedon = :now
         WHERE recordid = :id
    """, st=status, now=utcnow(), doc=documentid, id=recordid)
    if status == "finished":
        # It came from outside, so the three go in together: it is on file, it needs reading, and
        # the office is told it arrived.
        _came_in(conn, acct, driverid, "BACKGROUND_SCREENING", "A background screening",
                 "driverreports", recordid)


@router.get("/trips/upcoming")
def upcoming_trips(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """The next trips on the book, and whether the people and vehicles on them may actually run.

    This is the whole point of the application in one list. A driver whose medical certificate
    lapsed is an abstraction until it is a named passenger on Thursday, and a compliance file that
    cannot answer "is tomorrow covered" is a filing cabinet."""
    acct = user["accountid"]
    today = localnow(user["timezone"]).date()
    trips = rows(conn, """
        SELECT t.recordid, t.externalid, t.tripdate, t.servicelevel,
               COUNT(l.recordid) AS legs,
               SUM(l.pickupat IS NOT NULL) AS started,
               SUM(l.dropoffat IS NOT NULL) AS finished,
               GROUP_CONCAT(DISTINCT CONCAT(COALESCE(d.firstname, ''), ' ',
                                            COALESCE(d.lastname, '')) SEPARATOR ', ') AS drivers,
               GROUP_CONCAT(DISTINCT d.recordid) AS driverids,
               GROUP_CONCAT(DISTINCT COALESCE(v.externalid, v.vin) SEPARATOR ', ') AS vehicles,
               GROUP_CONCAT(DISTINCT v.recordid) AS vehicleids
        FROM trips t
          LEFT JOIN triplegs l ON l.tripid = t.recordid
          LEFT JOIN drivers d ON d.recordid = l.driverid AND d.deleted IS NULL
          LEFT JOIN vehicles v ON v.recordid = l.vehicleid AND v.deleted IS NULL
        WHERE t.accountid = :a AND t.deleted IS NULL AND t.tripdate >= :from
        GROUP BY t.recordid, t.externalid, t.tripdate, t.servicelevel
        ORDER BY t.tripdate, t.externalid
        LIMIT 12
    """, a=acct, **{"from": today - timedelta(days=3)})
    if not trips:
        return {"trips": [], "from": str(today)}

    # Who cannot drive and what cannot go out, worked out once for the whole list rather than once
    # per trip - the same engine the dashboard and the roster read.
    stopped, grounded = set(), set()
    for d in {x for t in trips for x in (t["driverids"] or "").split(",") if x}:
        hired = row(conn, "SELECT hiredon FROM drivers WHERE recordid = :d", d=d) or {}
        if not hired.get("hiredon"):
            stopped.add(d)
            continue
        if any(i["applies"] is True and i["gate"] == "hardstop"
               and i["status"] in (*ADVERSE_STATUS, "pending")
               for i in rules.for_driver(conn, acct, d,
                                         factset.assemble(conn, acct, d)["facts"], today=today)):
            stopped.add(d)
    for v in {x for t in trips for x in (t["vehicleids"] or "").split(",") if x}:
        if any(i["applies"] is True and i["gate"] == "hardstop"
               and i["status"] in (*ADVERSE_STATUS, "pending")
               for i in rules.for_vehicle(conn, acct, v,
                                          factset.assemble(conn, acct, vehicleid=v)["facts"],
                                          today=today)):
            grounded.add(v)

    out = []
    for t in trips:
        ds = [x for x in (t["driverids"] or "").split(",") if x]
        vs = [x for x in (t["vehicleids"] or "").split(",") if x]
        # Where the trip itself has got to. Read from the legs rather than stored, so it cannot
        # disagree with them: a trip is under way when a leg has been picked up and finished when
        # every leg has been dropped off.
        if not ds or not vs:
            state = "Unassigned"
        elif t["finished"] and t["finished"] == t["legs"]:
            state = "Completed"
        elif t["started"]:
            state = "In progress"
        else:
            state = "Upcoming"
        out.append({
            "recordid": t["recordid"], "externalid": t["externalid"],
            "tripdate": t["tripdate"], "servicelevel": t["servicelevel"],
            "drivers": (t["drivers"] or "").strip() or None,
            "vehicles": t["vehicles"] or None,
            "state": state,
            # Whether the people and vehicles on it may actually run. Carried beside the trip's own
            # state rather than instead of it: a trip can be perfectly scheduled for tomorrow and
            # still have a driver who may not drive.
            "driverbarred": any(d in stopped for d in ds),
            "vehiclebarred": any(v in grounded for v in vs),
        })
    return {"trips": out, "from": str(today)}


# What the first screen anybody opens has to say. Until this existed the dashboard showed arriving
# documents and nothing else, so an office could open TripProof, read "nothing is waiting", and not
# know its auto liability had lapsed or that the plan needed certifying next month. A thing nobody
# has to touch today still has to be visible before the day it stops the company.
@router.get("/attention")
def needs_attention(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Everything across the company, its drivers and its fleet that wants somebody.

    Three lists rather than one number: what is stopping something today, what is overdue or
    missing, and what runs out soon. A count on its own tells nobody what to do."""
    acct = user["accountid"]
    today = localnow(user["timezone"]).date()
    stops, owed, soon, toread = [], [], [], []
    roster, units = [], []

    def sort(where, who, link, items, since=None):
        for i in items:
            if i["applies"] is not True:
                continue
            # Nothing that starts at hiring is owed by somebody nobody has hired. The driver's own
            # page says so by grouping the list into stages; a dashboard that flattens it was
            # telling an office an applicant owed a W-4.
            if since is False and i.get("duestage") in ("athire", "ongoing"):
                continue
            # And nothing about somebody nobody has hired STOPS WORK. An applicant is not driving,
            # so an incomplete file of theirs stands between them and a hire - it does not stop the
            # business. It is outstanding, and it is the hiring screen's job, not the verdict's.
            stopping = i["gate"] == "hardstop" and since is not False
            joiner = "&" if "?" in link else "?"
            row_ = {"where": where, "who": who, "link": f'{link}{joiner}req={i["code"]}',
                    "code": i["code"], "name": i["name"], "why": i["why"],
                    "status": i["status"], "on": i["expireson"]}
            if i["status"] == "review":
                toread.append(row_)
            elif i["status"] in ("failed", "expired", "overdue"):
                (stops if stopping else owed).append(row_)
            elif i["status"] == "pending" and stopping:
                stops.append(row_)
            elif i["status"] == "pending":
                owed.append(row_)
            elif i["status"] == "expiring" and not i.get("scheduled"):
                # A monthly exclusion screening renews itself. Putting its routine turn beside an
                # expired medical certificate is how a dashboard teaches people to ignore it.
                soon.append(row_)

    company = factset.assemble(conn, acct)
    # The link carries the requirement, not just the page it is on. A dashboard that names a
    # problem and then hands somebody the page to go and find it on is a list of complaints.
    sort("company", None, "/company?tab=requirements",
         rules.for_company(conn, acct, company["facts"], today=today))

    for d in rows(conn, """
        SELECT recordid, firstname, lastname, hiredon FROM drivers
        WHERE accountid = :a AND deleted IS NULL AND stub = 0 AND terminatedon IS NULL
        ORDER BY lastname, firstname
    """, a=acct):
        who = f'{d["firstname"]} {d["lastname"]}'.strip().title()
        items = rules.for_driver(conn, acct, d["recordid"],
                                 factset.assemble(conn, acct, d["recordid"])["facts"], today=today)
        sort("driver", who, f'/drivers/{d["recordid"]}', items, since=bool(d["hiredon"]))
        # Whether this person may drive today, which is a different question from whether their
        # file is complete: an applicant with a perfect file still may not drive, because nobody
        # has hired them.
        barred = [i for i in items if i["applies"] is True and i["gate"] == "hardstop"
                  and i["status"] in (*ADVERSE_STATUS, "pending")]
        roster.append({
            "recordid": d["recordid"], "name": who, "link": f'/drivers/{d["recordid"]}',
            "hired": bool(d["hiredon"]),
            "eligible": bool(d["hiredon"]) and not barred,
            "why": ("Not hired yet" if not d["hiredon"]
                    else barred[0]["name"] if len(barred) == 1
                    else f"{len(barred)} requirements outstanding" if barred
                    else "Clear to drive"),
        })

    for v in rows(conn, """
        SELECT recordid, externalid, vin, make, model FROM vehicles
        WHERE accountid = :a AND deleted IS NULL AND stub = 0 ORDER BY externalid, vin
    """, a=acct):
        who = v["externalid"] or v["vin"] or " ".join(
            x for x in (v["make"], v["model"]) if x) or "A vehicle"
        items = rules.for_vehicle(conn, acct, v["recordid"],
                                  factset.assemble(conn, acct, vehicleid=v["recordid"])["facts"],
                                  today=today)
        sort("vehicle", who, f'/vehicles/{v["recordid"]}', items)
        barred = [i for i in items if i["applies"] is True and i["gate"] == "hardstop"
                  and i["status"] in (*ADVERSE_STATUS, "pending")]
        units.append({
            "recordid": v["recordid"], "name": who, "link": f'/vehicles/{v["recordid"]}',
            "eligible": not barred,
            "why": (barred[0]["name"] if len(barred) == 1
                    else f"{len(barred)} requirements outstanding" if barred
                    else "Ready to dispatch"),
        })

    # Soonest first, because that is the order somebody works them in.
    soon.sort(key=lambda r: r["on"] or date.max)

    # How many of each are clear, so the headline is a fraction somebody can act on rather than a
    # total they have to count themselves.
    stopped = {r["who"] for r in stops if r["where"] == "driver"}
    grounded = {r["who"] for r in stops if r["where"] == "vehicle"}
    drivers = rows(conn, """
        SELECT COUNT(*) AS n FROM drivers WHERE accountid = :a AND deleted IS NULL AND stub = 0
          AND terminatedon IS NULL AND hiredon IS NOT NULL""", a=acct)[0]["n"]
    applicants = rows(conn, """
        SELECT COUNT(*) AS n FROM drivers WHERE accountid = :a AND deleted IS NULL AND stub = 0
          AND terminatedon IS NULL AND hiredon IS NULL""", a=acct)[0]["n"]
    fleet = rows(conn, """
        SELECT COUNT(*) AS n FROM vehicles WHERE accountid = :a AND deleted IS NULL AND stub = 0
    """, a=acct)[0]["n"]
    return {
        "stops": stops, "owed": owed, "soon": soon, "toread": toread,
        "roster": roster, "fleet": units,
        "summary": {
            "company": len([r for r in stops if r["where"] == "company"]),
            "drivers": drivers, "driversclear": drivers - len(stopped),
            "applicants": applicants,
            "vehicles": fleet, "vehiclesclear": fleet - len(grounded),
        },
    }


@router.get("/company/requirements")
def company_requirements(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """What is asked of the company itself, and where it stands on each of it.

    The same engine the driver screen reads. Nothing here is stored: the rules come from the
    catalog, the facts from what the company has said about itself, and the evidence from the
    documents already on file - so this cannot drift out of step with the filing cabinet."""
    acct = user["accountid"]
    gathered = factset.assemble(conn, acct)
    items = rules.for_company(conn, acct, gathered["facts"],
                              today=localnow(user["timezone"]).date())
    counted: dict[str, int] = {}
    for i in items:
        counted[i["status"]] = counted.get(i["status"], 0) + 1
    live = [i for i in items if i["applies"] is True]
    return {"items": items, "counts": counted,
            # What is actually wrong, as against what is merely on the list.
            "outstanding": [i["code"] for i in live
                            if i["status"] in ("pending", "expired", "failed", "overdue")],
            "stops": [i["code"] for i in live
                      if i["gate"] == "hardstop"
                      and i["status"] in ("pending", "expired", "failed", "overdue")],
            "types": {r["code"]: r["recordid"] for r in rows(conn, """
                SELECT code, recordid FROM credentialtypes
                WHERE subject = 'company' AND active = 1""")}}


# ------------------------------------------------------------------------------------------------
# The rest of the drug and alcohol program: trained supervisors, and the random draw
# ------------------------------------------------------------------------------------------------

# 49 CFR 382.603: at least sixty minutes on each, for every person who may determine reasonable
# suspicion. Held here rather than in the rule row because it is the number the screen checks
# against as somebody types.
TRAINING_MINUTES = 60

# 49 CFR 382.305. FMCSA may revise these each year, which is why they live in the application and
# not in a rule row: a change is one edit for every customer.
RANDOM_RATES = {"drug": 50, "alcohol": 10}
TEST_TYPES = {"drug": "Controlled substances", "alcohol": "Alcohol"}


@router.get("/company/supervisor-training")
def supervisor_training(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Who may determine reasonable suspicion here, and whether each of them is trained for it."""
    acct = user["accountid"]
    return {
        "minutes": TRAINING_MINUTES,
        # Everyone who may call a reasonable suspicion test, and whether they have signed their
        # own training record. The signature is the evidence - the durations are on the face of
        # the record they signed - so nothing here asks the office to type minutes in for
        # somebody else.
        "supervisors": rows(conn, """
            SELECT u.recordid AS userid, u.name, u.email, r.recordid AS roleid, r.since,
                   d.recordid AS signatureid, d.signedon, s.typedname
            FROM companyroles r
              JOIN users u ON u.recordid = r.userid
              LEFT JOIN documentsignatures d
                ON d.accountid = r.accountid AND d.ownertype = 'user' AND d.ownerid = r.userid
               AND d.doctype = 'SUPERVISOR_TRAINING_RECORD'
              LEFT JOIN signatures s ON s.recordid = d.signatureid
            WHERE r.accountid = :a AND r.role = 'supervisor' AND r.until IS NULL
              AND u.deleted IS NULL
            ORDER BY u.name
        """, a=acct),
    }


@router.get("/company/random-selections")
def random_selections(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """The draws made this year, against the rates FMCSA sets and the pool they were drawn from."""
    acct = user["accountid"]
    year = localnow(user["timezone"]).date().year
    drawn = rows(conn, """
        SELECT s.recordid, s.drawnon, s.testtype, s.poolsize, s.selected, s.performedby,
               s.documentid, s.note, u.name AS addedbyname
        FROM randomselections s LEFT JOIN users u ON u.recordid = s.addedby
        WHERE s.accountid = :a AND s.deleted IS NULL
        ORDER BY s.drawnon DESC, s.added DESC
    """, a=acct)
    # Who came out, and what happened to each of them. The draw is the event; this is whether
    # it was followed through, which is the half an audit actually asks about.
    for d in drawn:
        d["drivers"] = randompool.chosen(conn, acct, d["recordid"])
        d["tested"] = sum(1 for x in d["drivers"] if x["testid"])
        d["excused"] = sum(1 for x in d["drivers"] if x["excusedon"] and not x["testid"])
        d["outstanding"] = len(d["drivers"]) - d["tested"] - d["excused"]
    # The pool, from the one definition of who is in it. This used to count drivers whose
    # operation is `cdl` or `cdlheavy` and never looked at whether anybody had been enrolled -
    # a second pool, disagreeing with the one on each driver's own file.
    #
    # 382.305(b) sets the rate against the AVERAGE number of driver positions over the period,
    # not against the headcount today: a carrier running twenty drivers all year and one that
    # hired twenty in December owe very different numbers of tests, and a headcount cannot tell
    # them apart. Both are reported, because the average is what the rate is computed from and
    # the headcount is what somebody looking at the screen recognises.
    today = localnow(user["timezone"]).date()
    upto = min(today, date(year, 12, 31))
    pool = randompool.members_now(conn, acct)
    # Averaged over the period this carrier has HAD a pool, not from 1 January regardless. See
    # randompool.window: twelve days of one driver divided by a whole year reports a pool of
    # nothing, and a number nobody recognises is a number nobody trusts.
    since, upto = randompool.window(conn, acct, year, upto)
    mean = randompool.average(conn, acct, since, upto)
    thisyear = [d for d in drawn if d["drawnon"].year == year]
    done = {k: sum(d["selected"] or 0 for d in thisyear if d["testtype"] == k)
            for k in RANDOM_RATES}
    return {
        "year": year, "pool": pool, "average": round(mean, 1),
        "results": eligibility.RESULTS,
        "averagedsince": str(since) if since != date(year, 1, 1) else None,
        "rates": RANDOM_RATES, "types": TEST_TYPES,
        "selections": drawn,
        # What has been drawn this year against what the rate asks of a pool that size.
        "progress": {k: {"selected": done[k], "owed": randompool.owed(mean, RANDOM_RATES[k])}
                     for k in RANDOM_RATES},
    }


def _supervisor_record(conn: Connection, acct: str, userid: str | None,
                       claim: dict | None = None) -> tuple[dict, str]:
    """One supervisor's 382.603 record, and the filled HTML of the sheet for it.

    Keyed on the person, because the appointment is what creates the obligation - there is no
    record to point at until the supervisor makes one, and they make it by signing. With no
    user it answers the blank form: the company's own details filled in, because those are
    true of every copy, and every line about a person left ruled.

    `claim` is what the supervisor is stating as they sign, before it is stored. The form they
    read has to be the form they sign, so the same fill does both."""
    held = row(conn, """
        SELECT u.recordid AS userid, u.name AS supervisor, u.role AS supervisortitle,
               u.email AS supervisoremail, r.since AS designated,
               t.recordid, t.completedon, t.alcoholminutes, t.drugminutes, t.provider,
               t.note, t.documentid
        FROM users u
        LEFT JOIN companyroles r ON r.userid = u.recordid AND r.accountid = u.accountid
             AND r.role = 'supervisor' AND r.until IS NULL
        LEFT JOIN supervisortraining t ON t.userid = u.recordid AND t.accountid = u.accountid
             AND t.deleted IS NULL
        WHERE u.recordid = :u AND u.accountid = :a AND u.deleted IS NULL
        ORDER BY t.completedon DESC, t.added DESC LIMIT 1
    """, u=userid, a=acct) if userid else {}
    if userid and not held:
        raise HTTPException(404, "No such user")
    if claim:
        held = {**held, **claim}
    # The company's own wording if they have edited it, the published text otherwise - read the
    # same way every other policy is read. A company that rewrote this sheet signs the sheet it
    # rewrote, not the one we publish.
    mine = row(conn, "SELECT text FROM companypolicies WHERE accountid = :a AND code = :c",
               a=acct, c="SUPERVISOR_TRAINING_RECORD") or {}
    source = mine.get("text") or documents.company_policy("SUPERVISOR_TRAINING_RECORD")["text"]
    values = {**_policy_context(conn, acct, "SUPERVISOR_TRAINING_RECORD"),
              **_supervisor_blanks(held)}
    # The signing act hands its own signature in, because the copy that gets stored IS the copy
    # being signed - drawn a moment before the signature row exists, so there is nothing yet to
    # look up. Everything afterwards reads the stored copy, not this.
    #
    # Drawn in their own hand, the way every other signed document in here draws one: a web font
    # cannot be relied on wherever the sheet ends up, so the signature travels as a picture.
    drawn = claim.get("signature") if claim else None
    if drawn:
        values["supervisorsignature"] = (
            f'<img alt="{escape(drawn["typedname"])}" style="height:34px;vertical-align:middle"'
            f' src="{applicationview.signature_image(drawn["typedname"], drawn["fontkey"])}">')
        values["supervisorsignedon"] = f'{drawn["signedon"]:%m/%d/%Y}'
    return held, documents.fill_exact(source, values)


@router.get("/company/supervisor-training/{userid}/signed")
def signed_supervisor_record(userid: str, user: dict = Depends(current_user),
                             conn: Connection = Depends(get_conn)):
    """What this supervisor signed, as they signed it."""
    acct = user["accountid"]
    said = signatures.signed(conn, acct, userid, ownertype="user").get(
        "SUPERVISOR_TRAINING_RECORD")
    if not said:
        raise HTTPException(404, "They have not signed a training record")
    who = row(conn, "SELECT name FROM users WHERE recordid = :u AND accountid = :a",
              u=userid, a=acct) or {}
    return {"title": signatures.DOC_TYPES["SUPERVISOR_TRAINING_RECORD"],
            "who": who.get("name"), "html": _with_stamp(said["signedtext"], said),
            "signedon": str(said["signedon"]), "signedby": said["typedname"]}


# ------------------------------------------------------------------------------------------------
# The supervisor's own acknowledgment - 49 CFR 382.603.
#
# Somebody else recording that a supervisor was trained is not the supervisor saying they were.
# The person who will decide whether a driver is sent for a reasonable suspicion test signs
# their own record, and until they have, the training is on file as an assertion about them
# rather than by them.
# ------------------------------------------------------------------------------------------------

def _supervisor_owes(conn: Connection, acct: str, userid: str) -> bool:
    """Whether this user holds the supervisor appointment and has not signed for it.

    The appointment is what creates the obligation. There is nothing else to wait for: the
    office does not record the training first, because 382.603 is about the person who will
    decide whether a driver is sent for a test, and what they did is theirs to state."""
    return bool(row(conn, """
        SELECT 1 AS x FROM companyroles r
        WHERE r.accountid = :a AND r.userid = :u AND r.role = 'supervisor' AND r.until IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM documentsignatures d
            WHERE d.accountid = r.accountid AND d.ownertype = 'user' AND d.ownerid = r.userid
              AND d.doctype = 'SUPERVISOR_TRAINING_RECORD')
        LIMIT 1
    """, a=acct, u=userid))


@router.get("/me/supervisor-record")
def my_supervisor_record(user: dict = Depends(current_user),
                         conn: Connection = Depends(get_conn)):
    """What this user is being asked to sign, and whether they already have."""
    acct = user["accountid"]
    held = signatures.signed(conn, acct, user["recordid"], ownertype="user")
    already = held.get("SUPERVISOR_TRAINING_RECORD")
    owed = (not user.get("platformrole")) and _supervisor_owes(conn, acct, user["recordid"])
    # Nothing to sign is an answer, and it has to SAY which answer. A dialog that opens on an
    # empty page because the person looking is not the person it is for is a dialog that looks
    # broken - which is exactly how it was read.
    if not owed and not already:
        who = rows(conn, """
            SELECT u.name FROM companyroles r JOIN users u ON u.recordid = r.userid
            WHERE r.accountid = :a AND r.role = 'supervisor' AND r.until IS NULL
              AND u.deleted IS NULL ORDER BY u.name
        """, a=acct)
        names = ", ".join(w["name"] for w in who)
        return {"owed": False, "signed": None, "html": None,
                "title": signatures.DOC_TYPES["SUPERVISOR_TRAINING_RECORD"],
                "because": (
                    "You are signed in as TripProof staff. A supervisor signs their own "
                    f"training record - {names} must sign in and sign it." if user.get("platformrole") and names
                    else "You are signed in as TripProof staff, and nobody here holds the "
                         "supervisor appointment yet." if user.get("platformrole")
                    else f"You do not hold the supervisor appointment. {names} does - "
                         "it is theirs to sign." if names
                    else "Nobody holds the supervisor appointment, so there is no training "
                         "record to sign. Appoint somebody on Company Requirements first.")}
    body = None
    if owed:
        _, body = _supervisor_record(conn, acct, user["recordid"])
    return {
        "owed": owed,
        "html": body,
        "minutes": TRAINING_MINUTES,
        "title": signatures.DOC_TYPES["SUPERVISOR_TRAINING_RECORD"],
        # The words that were signed, read back from the signature rather than re-rendered -
        # the record can change after it is signed, and the copy somebody put their name to
        # does not.
        "signed": ({"signedon": str(already["signedon"]), "typedname": already["typedname"],
                    "fontkey": already["fontkey"], "html": _with_stamp(already["signedtext"], already)}
                   if already else None),
    }


@router.get("/account/users/{userid}/supervisor-record")
def their_supervisor_record(userid: str, user: dict = Depends(account_admin),
                            conn: Connection = Depends(get_conn)):
    """Somebody else's signed training record, for the people who manage the roster.

    Read only, and only what was SIGNED. An admin may look at what a supervisor put their name
    to; nobody may sign it for them, so there is no unsigned copy offered here - that one is
    the supervisor's own to read and answer."""
    acct = user["accountid"]
    held = signatures.signed(conn, acct, userid, ownertype="user").get(
        "SUPERVISOR_TRAINING_RECORD")
    if not held:
        raise HTTPException(404, "They have not signed a training record")
    return {"owed": False, "html": None,
            "title": signatures.DOC_TYPES["SUPERVISOR_TRAINING_RECORD"],
            "signed": {"signedon": str(held["signedon"]), "typedname": held["typedname"],
                       "fontkey": held["fontkey"], "html": _with_stamp(held["signedtext"], held)}}


@router.post("/me/supervisor-record/sign")
async def sign_my_supervisor_record(
    request: Request,
    completedon: date = Form(...),
    alcoholminutes: int = Form(...),
    drugminutes: int = Form(...),
    provider: str | None = Form(None),
    note: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: dict = Depends(current_user),
    conn: Connection = Depends(get_conn),
):
    """State the training and sign for it, in one act.

    Section 4 of the record and section 6 of it are the same statement: the supervisor says
    what they did and puts their name to it. Splitting them would put the particulars in
    somebody else's hands and leave the acknowledgment standing over an empty section."""
    acct = user["accountid"]
    # A launched session is us standing in their office, not us being them. 49 CFR 382.603 is
    # satisfied by the person who will decide whether a driver is sent for a test saying they
    # were trained - support staff cannot say it for them.
    if user.get("platformrole"):
        raise HTTPException(403, "TripProof staff cannot sign a customer's training record - "
                                 "the supervisor signs their own")
    if not _supervisor_owes(conn, acct, user["recordid"]):
        raise HTTPException(409, "You do not hold the supervisor appointment, or have already "
                                 "signed your training record.")
    sig = signatures.current(conn, acct, "user", user["recordid"])
    if not sig:
        raise HTTPException(409, "Set up your signature first, then sign this.")
    if completedon > localnow(user["timezone"]).date():
        raise HTTPException(400, "That date has not happened yet")
    # 382.603(b) sets the floor at sixty minutes each. A record stating less is a record that
    # says the training did not meet the section, so it is refused here rather than filed and
    # counted.
    if alcoholminutes < TRAINING_MINUTES or drugminutes < TRAINING_MINUTES:
        raise HTTPException(400, f"49 CFR 382.603 asks for at least {TRAINING_MINUTES} minutes "
                                 f"on alcohol misuse and {TRAINING_MINUTES} on controlled "
                                 f"substances.")
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    # Drawn before it is recorded, so the sheet carries the signature it was signed with and
    # the stamp under it agrees with the row in the table.
    when = utcnow()
    claim = {"completedon": completedon, "alcoholminutes": alcoholminutes,
             "drugminutes": drugminutes, "provider": (provider or "").strip()[:160] or None,
             "note": (note or "").strip()[:512] or None, "documentid": documentid,
             "signature": {"typedname": sig["typedname"], "fontkey": sig["fontkey"],
                           "signername": sig["signername"], "recordid": sig["recordid"],
                           "ip": client_ip(request), "signedon": when}}
    recordid = newid()
    run(conn, """
        INSERT INTO supervisortraining (recordid, accountid, userid, completedon, alcoholminutes,
                                        drugminutes, provider, documentid, note, addedby)
        VALUES (:id, :a, :u, :on, :am, :dm, :p, :doc, :n, :by)
    """, id=recordid, a=acct, u=user["recordid"], on=completedon, am=alcoholminutes,
        dm=drugminutes, p=claim["provider"], doc=documentid, n=claim["note"],
        by=user["recordid"])
    _, rendered = _supervisor_record(conn, acct, user["recordid"], claim)
    signatures.sign(conn, acct, sig["recordid"], "SUPERVISOR_TRAINING_RECORD",
                    user["recordid"], rendered, ownertype="user", signedon=when,
                    ip=client_ip(request), useragent=request.headers.get("user-agent"))
    log(conn, user, "supervisor-training-signed", "company", acct,
        {"training": recordid, "completedon": str(completedon)}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


# ------------------------------------------------------------------------------------------------
# The bloodborne pathogens exposure determination - 29 CFR 1910.1030(c)(2).
#
# Made here rather than ticked somewhere else. The section asks the employer to work out which
# job classifications have occupational exposure, write it down, and certify it - and the answer
# is the fact every driver's bloodborne pathogens training hangs on, so the written page and the
# fact have to be the same thing.
# ------------------------------------------------------------------------------------------------

def _exposure_record(conn: Connection, acct: str, determinationid: str | None,
                     claim: dict | None = None) -> tuple[dict, str]:
    """One determination, and the filled HTML of the sheet for it.

    With no determination it answers the blank form - the company's own details, and every line
    about a decision nobody has made left ruled."""
    held = row(conn, """
        SELECT d.recordid, d.assessedon, d.exposed, d.nextreview, d.changes, d.corrective,
               u.name AS representative, u.role AS reptitle
        FROM exposuredeterminations d
        LEFT JOIN users u ON u.recordid = d.addedby
        WHERE d.recordid = :i AND d.accountid = :a
    """, i=determinationid, a=acct) if determinationid else {}
    if determinationid and not held:
        raise HTTPException(404, "No such determination")
    if claim:
        held = {**held, **claim}
    duties = (exposure.duties_of(conn, determinationid) if determinationid else [])
    if claim and claim.get("duties") is not None:
        duties = claim["duties"]
    blank = SUPERVISOR_BLANK
    mine = row(conn, "SELECT text FROM companypolicies WHERE accountid = :a AND code = :c",
               a=acct, c="BBP_EXPOSURE_DETERMINATION") or {}
    source = mine.get("text") or documents.company_policy("BBP_EXPOSURE_DETERMINATION")["text"]
    values = {
        **_policy_context(conn, acct, "BBP_EXPOSURE_DETERMINATION"),
        "assessedon": (f'{held["assessedon"]:%m/%d/%Y}' if held.get("assessedon") else blank),
        "preparedby": held.get("representative") or blank,
        "nextreview": (f'{held["nextreview"]:%m/%d/%Y}' if held.get("nextreview") else blank),
        # The three tables, written from the ticks rather than left as a frame to write in -
        # which is the whole difference between a determination and a form about one.
        **exposure.tables(duties),
        # 1910.1030(c)(2) is answered either way. "No" is a determination and prints as one.
        "exposurefound": ("Yes" if held["exposed"] else "No") if held.get("assessedon") else blank,
        "changes": held.get("changes") or blank,
        "corrective": held.get("corrective") or blank,
        "representative": held.get("representative") or blank,
        "reptitle": (held.get("reptitle") or "").title() or blank,
        "repsignature": blank,
        "repsignedon": blank,
    }
    drawn = claim.get("signature") if claim else None
    if drawn:
        values["repsignature"] = (
            f'<img alt="{escape(drawn["typedname"])}" style="height:34px;vertical-align:middle"'
            f' src="{applicationview.signature_image(drawn["typedname"], drawn["fontkey"])}">')
        values["repsignedon"] = f'{drawn["signedon"]:%m/%d/%Y}'
    return held, documents.fill_exact(source, values)


@router.get("/company/exposure-determination")
def exposure_determination(user: dict = Depends(current_user),
                           conn: Connection = Depends(get_conn)):
    """What this company has determined, and everything it determined before."""
    acct = user["accountid"]
    held = exposure.current(conn, acct)
    # Whether the person looking may certify one, so the screen can say so instead of
    # offering the whole form and refusing it at the end. A launched support session is us
    # standing in their office, not us being them.
    staff = bool(user.get("platformrole"))
    return {
        "duties": exposure.DUTIES,
        "short": exposure.DUTY_SHORT,
        "maycertify": not staff,
        "because": ("You are signed in as TripProof staff. A company determines its own "
                    "exposure - somebody who works here has to certify it." if staff else None),
        "current": held,
        "ticked": exposure.duties_of(conn, held["recordid"]) if held else [],
        "history": exposure.history(conn, acct),
        # What the determination decides, read back the way the engine reads it, so the screen
        # and the drivers' requirements can never be showing different answers.
        "exposed": exposure.exposed(conn, acct),
    }


class ExposureIn(BaseModel):
    assessedon: date
    # Which of the duties in app/exposure.py the company's work involves. The answer to
    # 1910.1030(c)(2) is computed from these rather than sent alongside them, so the two can
    # never disagree on the signed page.
    duties: list[str] = []
    nextreview: date | None = None
    changes: str | None = None
    corrective: str | None = None


@router.post("/company/exposure-determination")
def make_exposure_determination(body: ExposureIn, request: Request,
                                user: dict = Depends(account_admin),
                                conn: Connection = Depends(get_conn)):
    """Make the determination and certify it, in one act.

    Section 9 is the certification and sections 3 to 7 are what is being certified, so they are
    saved together and signed together. A determination recorded now and signed later would be
    a page asserting something nobody had yet put their name to."""
    acct = user["accountid"]
    if user.get("platformrole"):
        raise HTTPException(403, "TripProof staff cannot certify a customer's exposure "
                                 "determination - the company determines its own")
    sig = signatures.current(conn, acct, "user", user["recordid"])
    if not sig:
        raise HTTPException(409, "Set up your signature first, then certify this.")
    if body.assessedon > localnow(user["timezone"]).date():
        raise HTTPException(400, "That date has not happened yet")
    unknown = [d for d in body.duties if d not in exposure.DUTIES]
    if unknown:
        raise HTTPException(400, f"Unknown duty: {', '.join(unknown)}")
    kept = [k for k in exposure.DUTIES if k in set(body.duties)]
    when = utcnow()
    recordid = exposure.make(
        conn, acct, user["recordid"], assessedon=body.assessedon, duties=kept,
        nextreview=body.nextreview, changes=body.changes, corrective=body.corrective)
    claim = {"assessedon": body.assessedon, "exposed": bool(kept),
             "nextreview": body.nextreview, "changes": body.changes,
             "corrective": body.corrective, "duties": kept,
             "representative": user["name"], "reptitle": user.get("role"),
             "signature": {"typedname": sig["typedname"], "fontkey": sig["fontkey"],
                           "signedon": when}}
    _, rendered = _exposure_record(conn, acct, recordid, claim)
    # Owned by the determination, not by the person: a company reassesses every year, and a
    # signature keyed to the signer would overwrite last year's page with this year's.
    signatures.sign(conn, acct, sig["recordid"], "BBP_EXPOSURE_DETERMINATION",
                    recordid, rendered, ownertype="exposure", signedon=when,
                    ip=client_ip(request), useragent=request.headers.get("user-agent"))
    log(conn, user, "exposure-determined", "company", acct,
        {"determination": recordid, "exposed": bool(kept), "duties": kept},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True, "recordid": recordid}


@router.get("/company/exposure-determination/{recordid}/signed")
def signed_exposure_determination(recordid: str, user: dict = Depends(current_user),
                                  conn: Connection = Depends(get_conn)):
    """The determination as it was certified."""
    acct = user["accountid"]
    said = signatures.signed(conn, acct, recordid, ownertype="exposure").get(
        "BBP_EXPOSURE_DETERMINATION")
    if not said:
        raise HTTPException(404, "That determination was not certified")
    return {"title": signatures.DOC_TYPES["BBP_EXPOSURE_DETERMINATION"],
            "html": _with_stamp(said["signedtext"], said),
            "signedon": str(said["signedon"]), "signedby": said["typedname"]}


@router.delete("/company/exposure-determination/{recordid}")
def withdraw_exposure_determination(recordid: str, request: Request,
                                    user: dict = Depends(account_admin),
                                    conn: Connection = Depends(get_conn)):
    """Take back a determination filed in error.

    The row stays with a date on it. Withdrawing the one in force puts the previous one back,
    and where there is no previous one the company is back to not having determined - which is
    what an inspector would find, and so is what the drivers' requirements show."""
    acct = user["accountid"]
    if not exposure.withdraw(conn, acct, recordid, user["recordid"]):
        raise HTTPException(404, "No such determination")
    log(conn, user, "exposure-withdrawn", "company", acct, {"determination": recordid},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.get("/company/map")
def company_map(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """The dashboard map: the company's base, and where each driver last reported.

    The base is geocoded once and kept, so this is a database read on every call but the
    first. Drivers come from the positions that have been reported - an empty list is an
    empty list, not their home addresses."""
    acct = user["accountid"]
    base = wheremap.base_of(conn, acct)
    drivers = wheremap.drivers_at(conn, acct)
    # Last, and only here: saved() commits AND CLOSES the connection, so anything that reads
    # after it is reading a closed transaction. Looking the base up writes the position back
    # to the account, which is why there is a commit on a GET at all.
    if base:
        saved(conn)
    return {"base": base, "drivers": drivers, "style": wheremap.style_url(),
            "enroute": wheremap.enroute(drivers)}


class BasePositionIn(BaseModel):
    latitude: float
    longitude: float


@router.put("/company/map/base")
def set_base_position(body: BasePositionIn, request: Request,
                      user: dict = Depends(account_admin),
                      conn: Connection = Depends(get_conn)):
    """Move the base pin to where it actually is.

    OpenStreetMap does not hold every US street - it does not hold this company's own - so the
    geocoder lands on the town and the only thing that knows better is somebody who works
    there. Dragging the pin is that, and it sticks."""
    if not (-90 <= body.latitude <= 90 and -180 <= body.longitude <= 180):
        raise HTTPException(400, "That is not a position on Earth")
    if not wheremap.set_base(conn, user["accountid"], body.latitude, body.longitude):
        raise HTTPException(404, "No such company")
    log(conn, user, "base-position-set", "company", user["accountid"],
        {"lat": body.latitude, "lng": body.longitude}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


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
    # Who this schedule applies to - exactly one of the three.
    privatepay: bool = False
    payerkinds: list[str] = []
    payerids: list[str] = []
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
            SELECT recordid, name, category FROM payers
            WHERE active = 1 AND (accountid IS NULL OR accountid = :a)
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
    return {"categories": rateset.CATEGORIES,
            "payers": rateset.payers(conn, user["accountid"])}


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
        raise HTTPException(409, f"{using} schedule(s) or trip(s) still name this payer. "
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
        SELECT recordid, name, effectivefrom, effectiveto FROM payerschedules
        WHERE recordid = :i AND accountid = :a
    """, i=body.supersedes, a=accountid)
    if not old:
        raise HTTPException(404, "No such fee schedule to replace")
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


def _one_price_at_a_time(conn: Connection, accountid: str, body,
                         scheduleid: str | None = None) -> None:
    """Refuse a second live price list for the same payer over the same days.

    Refused at the moment it is written, not warned about once a trip has been priced from
    the wrong one. Two live schedules for one payer is not a preference - it is a question
    the pricing has no way to answer, and it would be settled silently by whichever started
    later.
    """
    if not body.active:
        return                      # a retired list competes with nothing
    if not body.privatepay and not body.payerkinds and not body.payerids:
        raise HTTPException(400, "Say who this schedule applies to")
    bad = [k for k in body.payerkinds if k not in rateset.CATEGORIES]
    if bad:
        raise HTTPException(400, f"Unknown payer kind {bad[0]}")
    other = rateset.clashes(conn, accountid, privatepay=body.privatepay,
                            payerkinds=body.payerkinds, payerids=body.payerids,
                            effectivefrom=body.effectivefrom or date.today(),
                            effectiveto=body.effectiveto, scheduleid=scheduleid)
    if not other:
        return
    ran = other["effectivefrom"].strftime("%m/%d/%Y")
    until = other["effectiveto"].strftime("%m/%d/%Y") if other["effectiveto"] else None
    raise HTTPException(409,
        f"{other['name']} already covers {other['over']} from {ran}"
        + (f" to {until}" if until else " onwards")
        + ". Give that one an end date, or start this one after it finishes.")


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
    _one_price_at_a_time(conn, acct, body)
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
    _one_price_at_a_time(conn, acct, body, scheduleid)
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

    Both directions through one endpoint, because it is one flag. Reinstating is gated the
    same way a save is: a schedule brought back must not collide with whatever has been
    covering its payers since it went.
    """
    acct = user["accountid"]
    held = rateset.schedule(conn, acct, scheduleid)
    if not held:
        raise HTTPException(404, "No such fee schedule")
    if body.active:
        other = rateset.clashes(
            conn, acct, privatepay=bool(held["privatepay"]),
            payerkinds=[k for k in (held.get("payerkinds") or "").split(",") if k],
            payerids=held.get("payerids") or [],
            effectivefrom=held["effectivefrom"], effectiveto=held["effectiveto"],
            scheduleid=scheduleid)
        if other:
            raise HTTPException(409,
                f"{other['name']} covers {other['over']} over those dates now. "
                "End that one first.")
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


# ------------------------------------------------------------------------------------------------
# The FMCSA Drug and Alcohol Clearinghouse: the EMPLOYER's account, not the driver's queries
# ------------------------------------------------------------------------------------------------

class ClearinghouseIn(BaseModel):
    registered: bool | None = None
    verifiedon: date | None = None
    ctpaused: bool | None = None
    ctpaname: str | None = None
    queryplan: bool | None = None
    note: str | None = None


@router.get("/company/clearinghouse")
def clearinghouse_registration(user: dict = Depends(current_user),
                               conn: Connection = Depends(get_conn)):
    """The state of this company's employer account at the FMCSA Clearinghouse.

    Not a document. There is no Clearinghouse registration form to complete and file - the account
    is established electronically at FMCSA - so what is held here is whether it exists, who
    confirmed it and when, whether a consortium or third party administrator acts for the company,
    and whether a query plan has been bought."""
    acct = user["accountid"]
    held = row(conn, """
        SELECT r.registered, r.verifiedon, r.lastverifiedon, r.ctpaused, r.ctpaname, r.queryplan,
               r.documentid, r.note, r.updated, u.name AS updatedbyname
        FROM clearinghouseregistration r LEFT JOIN users u ON u.recordid = r.updatedby
        WHERE r.accountid = :a
    """, a=acct)
    return {
        "registration": held,
        "usdot": (row(conn, "SELECT usdot FROM accounts WHERE recordid = :a", a=acct)
                  or {}).get("usdot"),
        # Where it is done, because the answer to "what do I upload" is "nothing, go here".
        "where": "https://clearinghouse.fmcsa.dot.gov/",
        # The driver side is a different obligation and is tracked on each driver's own file. Said
        # here so nobody records a driver's query against the company's account.
        "driverside": "The pre-employment query, the annual query and the violation and "
                      "return-to-duty reporting are tracked on each driver's own requirements.",
    }


@router.put("/company/clearinghouse")
async def set_clearinghouse_registration(
    request: Request,
    registered: bool = Form(...),
    verifiedon: date | None = Form(None),
    ctpaused: bool = Form(False),
    ctpaname: str | None = Form(None),
    queryplan: bool = Form(False),
    note: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: dict = Depends(account_admin),
    conn: Connection = Depends(get_conn),
):
    """Record the employer account, and that somebody here has confirmed it."""
    acct = user["accountid"]
    today = localnow(user["timezone"]).date()
    if verifiedon and verifiedon > today:
        raise HTTPException(400, "That date has not happened yet")
    if ctpaused and not (ctpaname or "").strip():
        raise HTTPException(400, "Name the consortium or third party administrator")
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    run(conn, """
        INSERT INTO clearinghouseregistration (accountid, registered, verifiedon, lastverifiedon,
                                               ctpaused, ctpaname, queryplan, documentid, note,
                                               updatedby)
        VALUES (:a, :r, :on, :now, :c, :cn, :q, :doc, :n, :u)
        ON DUPLICATE KEY UPDATE registered = VALUES(registered), verifiedon = VALUES(verifiedon),
                                lastverifiedon = VALUES(lastverifiedon),
                                ctpaused = VALUES(ctpaused), ctpaname = VALUES(ctpaname),
                                queryplan = VALUES(queryplan),
                                documentid = COALESCE(VALUES(documentid),
                                                      clearinghouseregistration.documentid),
                                note = VALUES(note), updatedby = VALUES(updatedby),
                                updated = CURRENT_TIMESTAMP
    """, a=acct, r=int(registered), on=verifiedon, now=today, c=int(ctpaused),
        cn=(ctpaname or "").strip()[:160] or None, q=int(queryplan), doc=documentid,
        n=(note or "").strip()[:512] or None, u=user["recordid"])
    log(conn, user, "clearinghouse-registration", "company", acct,
        {"registered": registered, "queryplan": queryplan}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


# ------------------------------------------------------------------------------------------------
# The FMCSA biennial update (MCS-150), and the worksheet for filling it in
# ------------------------------------------------------------------------------------------------

FILING_METHODS = {
    "portal": "FMCSA Portal",
    "form": "Form MCS-150 through FMCSA support",
    "mail": "Posted to the Office of Registration",
}


def _mcs150_counts(conn: Connection, acct: str) -> dict:
    """The counts the official form asks for, from what this company already has on file.

    Only what the records actually answer. A count this application cannot work out is returned as
    None and shown as a blank to be filled in, because a worksheet that guesses at a number the
    carrier certifies to is worse than one that leaves a line empty."""
    drivers = rows(conn, """
        SELECT operation, operatescmv, licenseclass, hiredon, terminatedon
        FROM drivers WHERE accountid = :a AND deleted IS NULL AND stub = 0
    """, a=acct)
    working = [d for d in drivers if d["hiredon"] and not d["terminatedon"]]
    # A CDL holder is one whose licence says so. The class is what the licence carries, so this is
    # read off the licence rather than off whether anybody ran a Clearinghouse query for them.
    cdl = [d for d in working if (d["licenseclass"] or "").upper() in ("A", "B", "C")]

    vehicles = rows(conn, """
        SELECT seats, gvwr, forcompensation FROM vehicles
        WHERE accountid = :a AND deleted IS NULL AND stub = 0
    """, a=acct)

    def seats(lo, hi):
        return sum(1 for v in vehicles
                   if v["seats"] is not None and lo <= int(v["seats"]) <= hi)

    return {
        # The form counts the driver, so a driver on the books but not yet hired is not one.
        "driverstotal": len(working),
        "driverscdl": len(cdl),
        # 49 CFR 390.5 draws the line for a passenger vehicle at 9 and at 16 including the driver,
        # which is where the form's own bus categories sit.
        "vehicles": {
            "van_8_or_fewer": seats(1, 8),
            "bus_9_to_15": seats(9, 15),
            "bus_16_or_more": seats(16, 999),
            "unknownseats": sum(1 for v in vehicles if v["seats"] is None),
            "total": len(vehicles),
        },
        # What the carrier has to answer itself, named so the worksheet can say so rather than
        # leaving somebody to notice an empty box.
        "notheld": {
            "mileage": "Mileage for the last full calendar year. TripProof records odometer "
                       "readings against vehicles but not distance per trip, so it cannot total "
                       "a year.",
            "driversbyradius": "Drivers within and beyond a 100 mile radius, interstate and "
                               "intrastate. Nothing on file records which side of that line a "
                               "driver works.",
            "ownership": "Vehicles owned, term leased and trip leased. The fleet is recorded "
                         "without how each vehicle is held.",
            "operationclass": "Operation classification - authorised for hire, private, exempt and "
                              "the rest. Nobody has been asked.",
        },
    }


@router.get("/company/mcs150")
def mcs150(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """What is known for the biennial update, when the next one is due, and what has been filed.

    The due date is worked out from the USDOT number under 49 CFR 390.19(b) and never from the last
    filing. Everything the form asks for that TripProof holds is here to copy; everything it does
    not hold is named."""
    acct = user["accountid"]
    a = row(conn, """
        SELECT name, dba, address1, address2, city, state, zip, phone, fax, email, ein, usdot,
               mcnumber
        FROM accounts WHERE recordid = :a
    """, a=acct) or {}
    today = localnow(user["timezone"]).date()
    filings = rows(conn, """
        SELECT f.recordid, f.filedon, f.method, f.documentid, f.note, u.name AS filedbyname
        FROM mcs150filings f LEFT JOIN users u ON u.recordid = f.filedby
        WHERE f.accountid = :a AND f.deleted IS NULL
        ORDER BY f.filedon DESC, f.added DESC
    """, a=acct)
    last = filings[0] if filings else None
    # A filing discharges the cycle it belongs to, so the next one is worked out from the filing
    # rather than from today. With nothing filed, the deadline is still the number's own.
    due = (rules.usdot_next_due(a.get("usdot"), last["filedon"]) if last
           else rules.usdot_biennial(a.get("usdot"), today))
    return {
        "usdot": a.get("usdot"), "mcnumber": a.get("mcnumber"),
        "identity": {k: a.get(k) for k in
                     ("name", "dba", "address1", "address2", "city", "state", "zip", "phone",
                      "fax", "email", "ein")},
        "official": _policy_context(conn, acct).get("safetyline"),
        "due": due,
        "overdue": bool(due and last and due < today),
        "counts": _mcs150_counts(conn, acct),
        "methods": FILING_METHODS,
        "filings": filings,
        "where": {
            "portal": "https://portal.fmcsa.dot.gov/",
            "post": "Federal Motor Carrier Safety Administration, Office of Registration (MC-RS), "
                    "1200 New Jersey Avenue SE, Room W65-206, Washington, DC 20590",
            "note": "Filed with FMCSA, not with the State. A form sent rather than filed through "
                    "the Portal must carry a copy of the government-issued identification of the "
                    "company official who signed it.",
        },
    }


@router.post("/company/mcs150")
async def record_mcs150_filing(
    request: Request,
    filedon: date = Form(...),
    method: str = Form(...),
    note: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: dict = Depends(account_admin),
    conn: Connection = Depends(get_conn),
):
    """Record that the biennial update went in, and keep the proof."""
    acct = user["accountid"]
    if method not in FILING_METHODS:
        raise HTTPException(400, "Say how it was filed")
    if filedon > localnow(user["timezone"]).date():
        raise HTTPException(400, "That date has not happened yet")
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    run(conn, """
        INSERT INTO mcs150filings (recordid, accountid, filedon, method, documentid, note, filedby)
        VALUES (:id, :a, :on, :m, :doc, :n, :u)
    """, id=newid(), a=acct, on=filedon, m=method, doc=documentid,
        n=(note or "").strip()[:512] or None, u=user["recordid"])
    log(conn, user, "mcs150-filed", "company", acct, {"filedon": str(filedon), "method": method},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.delete("/company/mcs150/{recordid}")
def remove_mcs150_filing(recordid: str, request: Request, user: dict = Depends(account_admin),
                         conn: Connection = Depends(get_conn)):
    """Withdraw a filing recorded in error. The row stays, dated, because somebody recorded it."""
    acct = user["accountid"]
    n = run(conn, """
        UPDATE mcs150filings SET deleted = :now
        WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, now=utcnow(), id=recordid, a=acct).rowcount
    if not n:
        raise HTTPException(404, "No such filing")
    log(conn, user, "mcs150-withdrawn", "company", acct, {"recordid": recordid},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


COMPANY_ROLES = {
    "der": "Designated Employer Representative",
    "supervisor": "Supervisor trained to determine reasonable suspicion",
    "safety": "Safety Manager",
    "security": "HIPAA Security Official",
    "bbpadmin": "Bloodborne pathogens plan administrator",
}


class RoleIn(BaseModel):
    userid: str


@router.get("/company/roles/{role}")
def company_role(role: str, user: dict = Depends(current_user),
                 conn: Connection = Depends(get_conn)):
    """Who holds this role, and who could."""
    if role not in COMPANY_ROLES:
        raise HTTPException(404, "No such role")
    acct = user["accountid"]
    return {
        "role": role, "name": COMPANY_ROLES[role],
        "held": rows(conn, """
            SELECT r.recordid, r.userid, r.since, u.name, u.email
            FROM companyroles r JOIN users u ON u.recordid = r.userid
            WHERE r.accountid = :a AND r.role = :r AND r.until IS NULL AND u.deleted IS NULL
            ORDER BY r.since DESC
        """, a=acct, r=role),
        # Everybody who could hold it. 49 CFR 40.3: an employee of the employer, which here means
        # somebody with a login of their own rather than a name typed into a box.
        "people": rows(conn, """
            SELECT recordid, name, email, role FROM users
            WHERE accountid = :a AND deleted IS NULL
              -- An auditor reads the file; they do not run the testing program.
              AND role <> 'auditor'
            ORDER BY name
        """, a=acct),
    }


@router.post("/company/roles/{role}")
def appoint_company_role(role: str, body: RoleIn, request: Request, tasks: BackgroundTasks,
                         user: dict = Depends(account_admin),
                         conn: Connection = Depends(get_conn)):
    """Appoint somebody to a company role."""
    if role not in COMPANY_ROLES:
        raise HTTPException(404, "No such role")
    acct = user["accountid"]
    who = row(conn, "SELECT recordid, name FROM users WHERE recordid = :u AND accountid = :a "
                    "AND deleted IS NULL", u=body.userid, a=acct)
    if not who:
        raise HTTPException(404, "No such person in this company")
    if row(conn, """SELECT 1 AS x FROM companyroles WHERE accountid = :a AND role = :r
                    AND userid = :u AND until IS NULL""", a=acct, r=role, u=body.userid):
        raise HTTPException(409, "They already hold it")
    run(conn, """
        INSERT INTO companyroles (recordid, accountid, role, userid, since, addedby)
        VALUES (:id, :a, :r, :u, :on, :by)
    """, id=newid(), a=acct, r=role, u=body.userid,
        on=localnow(user["timezone"]).date(), by=user["recordid"])
    log(conn, user, "role-appointed", "company", acct, {"role": role, "userid": body.userid},
        ip=client_ip(request))
    # A supervisor is the person who decides whether a driver is sent for a reasonable suspicion
    # test, and 49 CFR 382.603 asks them to be trained for it. Telling them they hold the
    # appointment is the first half; the second is that their own record is waiting for their
    # signature, because somebody else recording that they were trained is not them saying so.
    if role == "supervisor":
        them = row(conn, "SELECT name, email FROM users WHERE recordid = :u AND accountid = :a",
                   u=body.userid, a=acct)
        company = (row(conn, "SELECT name FROM accounts WHERE recordid = :a", a=acct)
                   or {}).get("name") or "your company"
        if them and (them.get("email") or "").strip():
            subject, html, text = emails.supervisor_appointed(
                them["name"], company,
                f"{settings.public_url.rstrip('/')}/company?sign=supervisor")
            tasks.add_task(mailer.send, them["email"], subject, html, text)
    saved(conn)
    return {"ok": True}


@router.delete("/company/roles/{role}/{recordid}")
def end_company_role(role: str, recordid: str, request: Request,
                     user: dict = Depends(account_admin),
                     conn: Connection = Depends(get_conn)):
    """End an appointment. The row stays and gets a date: who held a role and when is exactly the
    question an audit asks, and a deleted row cannot answer it."""
    acct = user["accountid"]
    r = run(conn, """UPDATE companyroles SET until = :on
                     WHERE recordid = :i AND accountid = :a AND role = :r AND until IS NULL""",
            on=localnow(user["timezone"]).date(), i=recordid, a=acct, r=role)
    if not r.rowcount:
        raise HTTPException(404, "That appointment is not current")
    log(conn, user, "role-ended", "company", acct, {"role": role}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.get("/company/qualifications")
def company_qualifications(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Every driver rule, what the regulation does with it, and what this company has elected."""
    acct = user["accountid"]
    chosen = {r["rulecode"]: r for r in rows(conn, """
        SELECT rulecode, applyto, reason FROM companyrulepolicy WHERE accountid = :a
    """, a=acct)}
    out = []
    for r in rows(conn, """
        SELECT code, name, description, authority, authoritytype, citation, grouping, duestage,
               gate, extendable, extendnote, offered, applieswhen, accountid, templatedocumentid,
               duedays, recurrence, recurrencedays, blocking
        FROM compliancerules WHERE subject = 'driver' AND effectiveto IS NULL
          AND (accountid IS NULL OR accountid = :acct)
        ORDER BY sortorder, name
    """, acct=acct):
        said = chosen.get(r["code"]) or {}
        # Who the regulation reaches, in the words the settings page needs. A rule with no
        # condition at all reaches everybody, and saying "required of some drivers" about it would
        # be worse than saying nothing.
        expr = rules.condition(r["applieswhen"])
        out.append({**{k: r[k] for k in ("code", "name", "description", "authority", "citation",
                                         "grouping", "duestage", "gate", "extendnote")},
                    "extendable": bool(r["extendable"]),
                    # Whether a law asks this at all. A contract requirement has no "where the law
                    # requires it" position, because no law requires it - and offering one is how a
                    # broker's term came to read as a regulation.
                    "bylaw": r["authoritytype"] != "contract",
                    # Ours to offer, nobody's to require. The page must not describe it as reaching
                    # anybody, because until this company adopts it nothing does.
                    "offered": bool(r["offered"]),
                    "universal": not expr and not r["offered"],
                    # Theirs, so the page can offer to retire it - and so it cannot offer to
                    # retire one of ours.
                    "own": r["accountid"] is not None,
                    "templatedocumentid": r["templatedocumentid"],
                    # Everything the form needs to open on what is already there, rather than on
                    # blanks somebody has to retype to change one field.
                    "audience": _audience_of(r["applieswhen"]),
                    "duedays": r["duedays"],
                    "expiresafterdays": r["recurrencedays"] if r["recurrence"] == "days" else None,
                    "blocking": bool(r["blocking"]),
                    "applyto": said.get("applyto") or "regulation",
                    "reason": said.get("reason")})
    return {"rules": out, "choices": ADOPTIONS, "audiences": {k: v[1] for k, v in AUDIENCE.items()},
            "stages": WHEN_DUE}


@router.put("/company/qualifications/{code}")
def set_company_qualification(code: str, body: PolicyIn, request: Request,
                              user: dict = Depends(account_admin),
                              conn: Connection = Depends(get_conn)):
    """Record what this company asks of drivers the regulation does not reach."""
    acct = user["accountid"]
    if body.applyto not in ADOPTIONS:
        raise HTTPException(400, "Unknown election")
    rule = row(conn, """SELECT code, extendable FROM compliancerules
                        WHERE code = :c AND subject = 'driver' AND effectiveto IS NULL
                          AND (accountid IS NULL OR accountid = :a)""", c=code, a=acct)
    if not rule:
        raise HTTPException(404, "No such requirement")
    if body.applyto == "alldrivers" and not rule["extendable"]:
        raise HTTPException(409, "This requirement cannot be asked of drivers it does not reach")
    run(conn, """
        INSERT INTO companyrulepolicy (accountid, rulecode, applyto, reason, updatedby)
        VALUES (:a, :c, :p, :r, :u)
        ON DUPLICATE KEY UPDATE applyto = VALUES(applyto), reason = VALUES(reason),
                                updated = CURRENT_TIMESTAMP, updatedby = VALUES(updatedby)
    """, a=acct, c=code, p=body.applyto, r=(body.reason or "").strip()[:200] or None,
        u=user["recordid"])
    log(conn, user, "qualification", "company", acct,
        {"code": code, "applyto": body.applyto}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


# Who a company's own requirement reaches. Deliberately three plain choices rather than the
# condition language the catalog uses: an operator writing down their own uniform policy is not
# going to compose a fact expression, and the three that matter are the three they have.
AUDIENCE = {
    "all": (None, "Every driver"),
    "cmv": ('{"fact":"driver.cmv","is":true}', "Drivers operating a commercial motor vehicle"),
    "noncmv": ('{"not":{"fact":"driver.cmv","is":true}}', "Drivers not operating a commercial "
                                                          "motor vehicle"),
}
WHEN_DUE = {"prehire": "Before hiring", "predrive": "Before driving",
            "athire": "Once hired", "ongoing": "Ongoing"}


def _audience_of(raw) -> str:
    """Which of the three audiences an expression is, for a form that offers three."""
    expr = rules.condition(raw)
    for key, (written, _) in AUDIENCE.items():
        if rules.condition(written) == expr:
            return key
    return "all"


def _own_rule(conn: Connection, acct: str, code: str) -> dict:
    got = row(conn, """SELECT recordid, code FROM compliancerules
                       WHERE code = :c AND accountid = :a AND subject = 'driver'
                         AND effectiveto IS NULL""", c=code, a=acct)
    if not got:
        raise HTTPException(404, "That is not one of your own requirements")
    return got


class OwnRuleIn(BaseModel):
    name: str
    description: str | None = None
    audience: str = "all"
    duestage: str = "prehire"
    duedays: int | None = None          # where it is owed after hire, by when
    expiresafterdays: int | None = None  # where the thing it asks for goes out of date
    blocking: bool = False               # does it stop the driver, or is it a deficiency
    reason: str | None = None            # the contract or policy behind it, for the file


@router.post("/company/qualifications")
async def add_company_requirement(request: Request,
                                  body: str = Form(...),
                                  template: UploadFile | None = File(None),
                                  user: dict = Depends(account_admin),
                                  conn: Connection = Depends(get_conn)):
    """A requirement this company asks for that nobody else has heard of.

    It goes into the same catalog as the regulations, with this account's id on it, which is the
    whole of what makes it work: the engine reads one table, so a company requirement gets the
    stages, the gates, the expiry arithmetic, the review rule, the dashboard and the validity panel
    without a line of code written for it. It is never shown to another account and our own
    migrations never touch it.
    """
    acct = user["accountid"]
    want = OwnRuleIn.model_validate_json(body)
    name = (want.name or "").strip()
    if not name:
        raise HTTPException(400, "Give the requirement a name")
    if want.audience not in AUDIENCE:
        raise HTTPException(400, "Unknown audience")
    if want.duestage not in WHEN_DUE:
        raise HTTPException(400, "Unknown stage")

    documentid = None
    if template is not None and template.filename:
        data = await template.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, template.filename,
                                  template.content_type, user["recordid"], origin=storage.OFFICE)

    # Generated rather than taken from the name, so that two companies inventing the same
    # requirement on the same day cannot collide in a table whose codes are global.
    code = f"CO_{secrets.token_hex(5).upper()}"
    typeid = newid()
    run(conn, """
        INSERT INTO credentialtypes (recordid, accountid, code, name, subject, description, active)
        VALUES (:id, :a, :c, :n, 'driver', :d, 1)
    """, id=typeid, a=acct, c=code, n=name[:128], d=(want.description or "").strip()[:512] or None)
    run(conn, """
        INSERT INTO compliancerules (recordid, accountid, subject, code, name, description,
                                     templatedocumentid, authoritytype, authority, citation,
                                     applieswhen, evidencekind, evidencesource, origin, extendable,
                                     reviewrequired, determination, blocking, gate, grouping,
                                     duestage, duedays, duetext, recurrence, recurrencedays,
                                     warndays, sortorder, effectivefrom)
        VALUES (:id, :a, 'driver', :c, :n, :d, :tpl, 'policy', 'Company policy', :why,
                :when, 'document', :src, 'thirdparty', 0, 0, 0, :blocking, :gate, 'company',
                :stage, :duedays, NULL, :recur, :days, 30, 900, CURRENT_DATE)
    """, id=newid(), a=acct, c=code, n=name[:160],
        d=(want.description or "").strip()[:600] or None, tpl=documentid,
        why=(want.reason or "").strip()[:160] or None,
        when=AUDIENCE[want.audience][0], src=f"credential:{code}",
        blocking=1 if want.blocking else 0,
        gate="hardstop" if want.blocking else "deficiency",
        stage=want.duestage, duedays=want.duedays,
        recur="days" if want.expiresafterdays else "once",
        days=want.expiresafterdays)
    log(conn, user, "requirement-added", "company", acct, {"code": code, "name": name},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True, "code": code}


@router.put("/company/qualifications/{code}/rule")
async def edit_company_requirement(code: str, request: Request,
                                   body: str = Form(...),
                                   template: UploadFile | None = File(None),
                                   user: dict = Depends(account_admin),
                                   conn: Connection = Depends(get_conn)):
    """Change one of this company's own requirements.

    Only their own: ours are the regulations, and a company editing the text of 49 CFR 391.23 in
    their own copy is how a file ends up citing something that does not say what it claims."""
    acct = user["accountid"]
    _own_rule(conn, acct, code)
    want = OwnRuleIn.model_validate_json(body)
    name = (want.name or "").strip()
    if not name:
        raise HTTPException(400, "Give the requirement a name")
    if want.audience not in AUDIENCE:
        raise HTTPException(400, "Unknown audience")
    if want.duestage not in WHEN_DUE:
        raise HTTPException(400, "Unknown stage")

    documentid = None
    if template is not None and template.filename:
        data = await template.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, template.filename,
                                  template.content_type, user["recordid"], origin=storage.OFFICE)

    run(conn, """
        UPDATE compliancerules
           SET name = :n, description = :d, citation = :why, applieswhen = :when,
               blocking = :blocking, gate = :gate, duestage = :stage, duedays = :duedays,
               recurrence = :recur, recurrencedays = :days,
               -- A template left off is a template kept. Clearing one is its own act, not
               -- something that happens because somebody edited the name.
               templatedocumentid = COALESCE(:tpl, templatedocumentid)
         WHERE code = :c AND accountid = :a
    """, c=code, a=acct, n=name[:160], d=(want.description or "").strip()[:600] or None,
        why=(want.reason or "").strip()[:160] or None, when=AUDIENCE[want.audience][0],
        blocking=1 if want.blocking else 0,
        gate="hardstop" if want.blocking else "deficiency",
        stage=want.duestage, duedays=want.duedays,
        recur="days" if want.expiresafterdays else "once", days=want.expiresafterdays,
        tpl=documentid)
    run(conn, "UPDATE credentialtypes SET name = :n WHERE code = :c AND accountid = :a",
        n=name[:128], c=code, a=acct)
    log(conn, user, "requirement-changed", "company", acct, {"code": code, "name": name},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.delete("/company/qualifications/{code}")
def retire_company_requirement(code: str, request: Request,
                               user: dict = Depends(account_admin),
                               conn: Connection = Depends(get_conn)):
    """Stop asking for one of this company's own requirements.

    Retired rather than deleted, and only ever one of their own. Everything already filed against
    it stays where it is: a driver's file is a record of what was asked and answered at the time,
    and a requirement vanishing out of it afterwards would make last year's file unreadable."""
    acct = user["accountid"]
    r = run(conn, """
        UPDATE compliancerules SET effectiveto = CURRENT_DATE
        WHERE code = :c AND accountid = :a AND subject = 'driver' AND effectiveto IS NULL
    """, c=code, a=acct)
    if not r.rowcount:
        raise HTTPException(404, "That is not one of your own requirements")
    run(conn, "UPDATE credentialtypes SET active = 0 WHERE code = :c AND accountid = :a",
        c=code, a=acct)
    log(conn, user, "requirement-retired", "company", acct, {"code": code}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


# A requirement answered by a determination rather than a document, and the column the answer
# lives in. Named here rather than taken from the request, so this endpoint can only ever write to
# a field that is one of these.
DRIVER_FACTS = {
    "driver.english": ("englishproficient",
                       "Can this driver read and speak English well enough to converse with the "
                       "public, understand highway traffic signs and signals, respond to official "
                       "inquiries, and make entries on reports and records?"),
}


def _fact_reading(conn: Connection, acct: str, driverid: str, which: str) -> dict | None:
    """What a derived fact was read FROM, so the dialog can show its working.

    A requirement nobody can answer still has to explain itself: the date it was read from, what
    that date makes true, and - where the date is missing - where to go and put it."""
    if which != "driver.age21":
        return None
    d = row(conn, """SELECT dob, TIMESTAMPDIFF(YEAR, dob, CURDATE()) AS age FROM drivers
                     WHERE recordid = :d AND accountid = :a""", d=driverid, a=acct) or {}
    return {"what": "Date of birth", "value": d.get("dob"), "age": d.get("age"),
            "where": "Driver Information"}


class FactIn(BaseModel):
    answer: bool | None = None


@router.post("/drivers/{driverid}/requirements/{code}/fact")
def answer_requirement_fact(driverid: str, code: str, body: FactIn, request: Request,
                            user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Record the carrier's determination on a requirement that has nothing to file.

    Answered here rather than on the driver's information page, because this is where somebody is
    dealing with the requirement. Three-valued all the way through: clearing it back to "not
    assessed" has to be possible, or a determination made by mistake can never be withdrawn."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    rule = row(conn, """SELECT evidencesource FROM compliancerules
                        WHERE code = :c AND subject = 'driver' AND effectiveto IS NULL
                          AND (accountid IS NULL OR accountid = :a)""", c=code, a=acct)
    if not rule:
        raise HTTPException(404, "No such requirement")
    want = (rule["evidencesource"] or "").partition(":")[2]
    if want not in DRIVER_FACTS:
        raise HTTPException(409, "That requirement is not answered this way")
    column = DRIVER_FACTS[want][0]
    run(conn, f"UPDATE drivers SET {column} = :v, updated = :now "
               "WHERE recordid = :d AND accountid = :a",
        v=None if body.answer is None else int(body.answer), now=utcnow(), d=driverid, a=acct)
    log(conn, user, "determination", "driver", driverid,
        {"code": code, "answer": body.answer}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "evaluation": evaluation}


@router.get("/drivers/{driverid}/requirements")
def driver_requirements(driverid: str, user: dict = Depends(current_user),
                        conn: Connection = Depends(get_conn)):
    """What is asked of this driver, why it is asked, and where they stand on each of it.

    Nothing here is stored. The rules are read from compliancerules, the facts are assembled from
    the company and the fleet, and the evidence is read from the records that already hold it - so
    this cannot drift out of step with the MVR, the review or the report the way the old
    qualification list did."""
    acct = user["accountid"]
    driver = _applicant(conn, acct, driverid)
    gathered = factset.assemble(conn, acct, driverid)
    items = rules.for_driver(conn, acct, driverid, gathered["facts"], today=localnow(user["timezone"]).date())

    # Before somebody is hired, the only question on the table is whether they can be. A road test
    # due on their first day and an annual review due twelve months in are real obligations and
    # they are not reasons to hold up a decision, so they are not put in front of the person
    # making one. Once hired, the whole file is theirs to keep - nothing is filtered away.
    hired = bool(driver.get("hiredon")) or driver["status"] in ("hired", "inactive")
    later = 0
    if not hired:
        keep = [i for i in items if i["duestage"] in ("prehire", "predrive", None)]
        later = len(items) - len(keep)
        items = keep

    counted: dict[str, int] = {}
    for i in items:
        counted[i["status"]] = counted.get(i["status"], 0) + 1
        # A requirement TripProof worked out for itself has nothing behind its Details button:
        # there is no document to look at, no history to read and nothing to file. The age rule is
        # the first of these - it is the date of birth and some arithmetic. One a person has to
        # ANSWER is a different thing and keeps its dialog.
        kind, _, which = (i["evidencesource"] or "").partition(":")
        i["readonly"] = kind == "driverfact" and which not in DRIVER_FACTS
    return {"items": items, "facts": gathered["facts"], "fleet": gathered["fleet"],
            "counts": counted, "hired": hired,
            # How many are being held back until they are hired, so the screen can say so rather
            # than quietly showing a shorter list than the file actually holds.
            "later": later,
            # A driver is held up by anything blocking that is failed, expired or still pending.
            "blocked": [i["code"] for i in items
                        if i["blocking"] and i["status"] in ("failed", "expired", "pending")],
            # And the narrower question dispatch actually asks: may this person drive today?
            "gate": _gate(conn, acct, driverid, items, gathered["facts"])}


def _attached(conn: Connection, accountid: str, driverid: str) -> bool:
    """Whether the driver sent return-to-duty paperwork with their questionnaire, or since."""
    app_ = row(conn, """
        SELECT data FROM driverapplications WHERE driverid = :d AND accountid = :a
        ORDER BY startedon DESC LIMIT 1
    """, d=driverid, a=accountid)
    try:
        step = ((json.loads(app_["data"] or "{}") if app_ else {}) or {}).get("steps", {}).get("10")
    except ValueError:
        step = None
    if step and step.get("attached"):
        return True
    # Or asked for separately and sent in since.
    return bool(row(conn, """
        SELECT 1 AS x FROM uploadrequests
        WHERE accountid = :a AND driverid = :d AND credentialcode = 'RTD_DOCUMENTATION'
          AND documentid IS NOT NULL
    """, a=accountid, d=driverid))


def _answered(conn: Connection, accountid: str, driverid: str, rule: dict, kind: str) -> list[dict]:
    """A requirement the driver ANSWERED rather than sent a document for, as a record.

    The answer itself is a fact and lives on their application, where the rule reads it - it is not
    copied here. What is here is the form it was answered on, drawn and signed at the moment they
    sent it, so the screen has something to open. Without this the dialog says nothing is on file
    while the row beside it asks somebody to go and read it."""
    if not kind.startswith("applicationanswer"):
        return []
    # Which submission answered this rule. Usually the one named after it, but one form can settle
    # more than one requirement - the questionnaire answers both the disclosure and the return to
    # duty - so the rule is matched on the fact it reads, not only on its own code.
    fact = (rule["evidencesource"] or "").partition(":")[2]
    codes = sorted({c for c, facts_ in rules.ANSWERS.items() if fact in facts_} | {rule["code"]})
    named = {f"c{i}": c for i, c in enumerate(codes)}
    found = rows(conn, f"""
        SELECT recordid, DATE(uploadedon) AS effectiveon, NULL AS expireson, 0 AS exempt,
               documentid, NULL AS determination, NULL AS note, uploadedon AS recordedon,
               'answered' AS source
        FROM uploadrequests
        WHERE accountid = :a AND driverid = :d
          AND credentialcode IN ({", ".join(f":{k}" for k in named)})
          AND uploadedon IS NOT NULL AND cancelledon IS NULL
        ORDER BY uploadedon DESC
    """, a=accountid, d=driverid, **named)
    return found


# What a hard stop looks like. A rule nobody has answered yet is not the same as one that came
# back badly, but neither of them is a driver who may be sent out: 49 CFR 382.301 does not say "may
# drive while we get round to the test".
#
# "ordered" is the awkward one, because it means two different things. A driving record sent for
# with nothing on file is a gap - the driver may not drive on a question nobody has answered. A
# licence that is valid until 2029 with a fresh copy asked of the driver is not a gap at all, and
# grounding somebody over it would be absurd. So an order only stops where nothing is behind it.
STOPPING = ("failed", "expired", "overdue", "pending", "review")
# Of those, the ones that are a verdict on the driver rather than work outstanding. "Return-to-duty
# in progress" is here because it is not a softer kind of prohibited: the driver may not perform
# safety-sensitive functions in either state, and the only difference is what the office does next.
ADVERSE_STATUS = ("failed", "expired", "overdue", "prohibited", "rtdinprogress")


def _stops(item: dict) -> bool:
    # Owed, and not yet. A requirement carrying a due date it has not reached is still `pending` -
    # the engine turns it to `overdue` on the day it passes - so a date here means time in hand,
    # and a driver is not stopped by work that is not due.
    if item["status"] == "pending" and item.get("dueon"):
        return False
    if item["status"] in STOPPING:
        return True
    return item["status"] == "ordered" and not item.get("on")


def _owed_now(item: dict, hired: bool) -> bool:
    """Whether this requirement is something the driver can be behind on today.

    An annual MVR review and an annual Clearinghouse query are obligations of employment. A driver
    who has never been taken on has nothing to be a year late for, and counting those against an
    applicant says "two things block this driver from driving" about work that cannot begin until
    after the decision this screen exists to make."""
    return hired or (item["duestage"] or "prehire") in ("prehire", "predrive")


def _gate(conn: Connection, accountid: str, driverid: str, items: list[dict],
          facts: dict | None = None) -> dict:
    """Can this driver be assigned a trip today?

    Deliberately narrower than "is the file complete". What stops a driver is a sentence somewhere
    saying they may not drive - an expired licence, an expired medical card, a prohibited drug and
    alcohol status, a query that is overdue. The I-9, the trainings and the policy receipts are
    real work the office owes, and they are not a reason to leave a trip uncovered this afternoon.
    """
    driver = _driver_for_rules(conn, accountid, driverid)
    transit = _transit(conn, accountid)
    da = eligibility.da_status(conn, accountid, driverid, driver, transit)
    # A violation this office never saw still counts. 49 CFR 40.25(j): an applicant who discloses a
    # positive or a refusal at an employer that did not hire them may not perform safety-sensitive
    # functions until the return-to-duty process has been completed, and a negative test taken here
    # does not answer it. There is no prohibition record because nothing happened here - the bar is
    # no less real for that, and the screen must not say "qualified" beside a stop.
    #
    # Read off the requirement rather than worked out again from the answers, so there is one
    # arithmetic: the rule already knows the difference between completed, claimed-but-undocumented
    # and not completed.
    disclosed = next((i for i in items if i["code"] == "PRIOR_VIOLATION_RTD"
                      and i.get("applies") is True), None)
    if da["status"] == "qualified" and disclosed and disclosed["status"] != "satisfied":
        da = {**da, "status": "prohibited", "why": disclosed["why"], "source": "disclosure"}
    hired = bool(driver.get("hiredon")) or driver["status"] in ("hired", "inactive")
    stops = [{"code": i["code"], "name": i["name"], "status": i["status"], "why": i["why"]}
             for i in items if i.get("gate") == "hardstop" and _stops(i) and _owed_now(i, hired)]
    if da["status"] in ("prohibited", "rtdinprogress"):
        stops.insert(0, {"code": "DA_STATUS", "name": "Drug and alcohol status",
                         "status": da["status"], "why": da["why"]})
    # Stopped and DISQUALIFIED are not the same thing, and a list that calls them both the second
    # one is a list that cries wolf. A pending driver with a licence copy still to come is not
    # barred from anything - they have never been cleared in the first place, and the work to
    # finish is what the dashboard counts. Disqualified means something came back against them: a
    # determination that failed, a record that ran out, an obligation that went past its date, or a
    # drug and alcohol prohibition. That is a sentence about the person; the rest is a queue.
    #
    # ONE definition, and the list IS the definition. It used to be two - this list, plus a second
    # clause adding the drug and alcohol bar - and they disagreed the moment a bar was anything
    # other than the words in this tuple. A driver in the return-to-duty process came out
    # disqualified by the second clause and absent from the first, so the roster showed a red pill
    # and the driver's own banner showed nothing at all. Whatever disqualifies somebody belongs in
    # here, where the thing that says so and the thing that lists why cannot come apart.
    adverse = [x for x in stops if x["status"] in ADVERSE_STATUS]
    return {
        "disqualified": bool(adverse),
        "adverse": adverse,
        "candrive": not stops,
        "stops": stops,
        # Everything else outstanding: owed, auditable, and not a reason to cancel a trip.
        "deficiencies": [{"code": i["code"], "name": i["name"], "status": i["status"]}
                         for i in items
                         if i.get("gate") != "hardstop" and i["blocking"] and _stops(i)],
        "dotdrugalcohol": {**da, "labels": eligibility.DA_STATUS},
        "clearinghouse": {**eligibility.clearinghouse(conn, accountid, driverid, driver),
                          "querylabels": eligibility.QUERY_STATUS,
                          "driverlabels": eligibility.DRIVER_STATUS},
    }


# How far ahead "upcoming" looks. Long enough that a medical card can be booked and a driving
# record pulled before the day it matters.
HORIZON_DAYS = 30


# A pending driver is not being managed, they are being DECIDED ON. Everything on their dashboard
# earns its place against one question - can this person be hired, and what stands between here and
# that decision - which is why nothing post-hire appears on it.
BAD_STATUS = ("failed", "expired")
# On file and in date today. A record that runs out next month is still a record today, and the
# requirements list marks it with the same green tick.
DONE_STATUS = ("satisfied", "expiring")


def _tally(mine: list[dict]) -> dict:
    """How far one of the two questions has got: what it asks for, and how much is on file today."""
    return {"total": len(mine),
            "done": len([i for i in mine if i["status"] in DONE_STATUS])}


@router.get("/drivers/{driverid}/standing")
def driver_standing(driverid: str, user: dict = Depends(current_user),
                    conn: Connection = Depends(get_conn)):
    """Whether this driver may perform safety-sensitive functions today, and what says they may not.

    Read on every section of the driver file rather than on one screen. A disqualification is not a
    fact somebody should have to go looking for: a driver who may not drive is the single most
    important thing anybody opening this file needs to know, and knowing it on the dashboard only
    is knowing it in the one place a dispatcher in a hurry does not look."""
    acct = user["accountid"]
    gathered = factset.assemble(conn, acct, driverid)
    items = rules.for_driver(conn, acct, driverid, gathered["facts"])
    gate = _gate(conn, acct, driverid, items, gathered["facts"])
    return {"candrive": gate["candrive"], "stops": gate["stops"],
            # What the banner shouts about. Everything in `stops` keeps a driver out of a vehicle;
            # only these say something came back against them.
            "disqualified": gate["disqualified"], "adverse": gate["adverse"],
            "dotdrugalcohol": gate["dotdrugalcohol"]}


@router.get("/drivers/{driverid}/dashboard")
def driver_dashboard(driverid: str, user: dict = Depends(current_user),
                     conn: Connection = Depends(get_conn)):
    """What somebody deciding whether to hire this driver needs in front of them."""
    acct = user["accountid"]
    driver = _driver_for_rules(conn, acct, driverid)
    gathered = factset.assemble(conn, acct, driverid)
    items = rules.for_driver(conn, acct, driverid, gathered["facts"])
    today = localnow(user["timezone"]).date()
    gate = _gate(conn, acct, driverid, items, gathered["facts"])
    # Which obligations are live depends on where the driver already is.
    #
    # Before hiring, only what bears on the decision. The I-9, the trainings and the annual review
    # are owed by somebody already on the books, and putting them in front of a hiring decision is
    # what the stages exist to prevent.
    #
    # Once they are hired that reason is gone - the decision has been made - and those at-hire and
    # ongoing obligations ARE the work. Holding them back from an active driver's dashboard left a
    # signed I-9 sitting in the engine as "waiting to be read" while the screen whose whole job is
    # to list what is waiting to be read said "Nothing to review".
    onbooks = driver["status"] in ("hired", "inactive")
    STAGES = ("prehire", "predrive", "athire", "ongoing") if onbooks else ("prehire", "predrive")
    live = [i for i in items if i["applies"] is True
            and (i["duestage"] or "prehire") in STAGES]
    later = len([i for i in items if i["applies"] is True
                 and (i["duestage"] or "prehire") not in STAGES])

    def card(i, extra=None):
        return {"code": i["code"], "name": i["name"], "status": i["status"], "why": i["why"],
                "duetext": i.get("duetext"), **(extra or {})}

    # 1. What came back BADLY, which is a different thing from what has not arrived. These are
    #    reasons to decline somebody; the rest is paperwork.
    adverse = [card(i) for i in live if i["status"] in BAD_STATUS]
    da = gate["dotdrugalcohol"]
    if da.get("status") in ("prohibited", "rtdinprogress"):
        adverse.insert(0, {"code": "DA_STATUS", "name": "Drug and alcohol status",
                           "status": da["status"], "why": da["why"]})

    # 2. Who each outstanding item is waiting on. "12 outstanding" is noise; "3 are waiting on you"
    #    is a list of things to do this morning.
    asked = {r["credentialcode"]: r for r in rows(conn, """
        SELECT u.credentialcode, u.senton, u.createdon, who.name AS askedby
        FROM uploadrequests u LEFT JOIN users who ON who.recordid = u.requestedby
        WHERE u.accountid = :a AND u.driverid = :d AND u.uploadedon IS NULL
          AND u.cancelledon IS NULL
    """, a=acct, d=driverid)}
    asked.update({r["credentialcode"]: r for r in rows(conn, """
        SELECT g.doctype AS credentialcode, g.senton, g.createdon, who.name AS askedby
        FROM signingrequests g LEFT JOIN users who ON who.recordid = g.requestedby
        WHERE g.accountid = :a AND g.driverid = :d AND g.signedon IS NULL
          AND g.cancelledon IS NULL
    """, a=acct, d=driverid)})
    ordered = {r["code"] for r in rows(conn, """
        SELECT code FROM driverreports
        WHERE accountid = :a AND driverid = :d AND receivedon IS NULL
    """, a=acct, d=driverid)}
    outside = bool(rows(conn, """
        SELECT 1 AS x FROM roadtests WHERE accountid = :a AND driverid = :d
          AND senton IS NOT NULL AND completedon IS NULL
    """, a=acct, d=driverid))
    employers_out = bool(rows(conn, """
        SELECT 1 AS x FROM employerinquiries WHERE accountid = :a AND driverid = :d
          AND respondedon IS NULL AND effortclosedon IS NULL
    """, a=acct, d=driverid))

    def days(r):
        when = r.get("senton") or r.get("createdon")
        return (today - when.date()).days if when else None

    waiting = {"driver": [], "outside": [], "office": []}
    for i in live:
        if i["status"] not in ("pending", "ordered", "unknown"):
            continue
        # A rollup is not a task. The driver qualification file is answered by the other rules
        # under 49 CFR 391, every one of which is already on this list in its own right, so
        # putting it here too only restates them: "Waiting on Annual inquiry and review of
        # driving record" beside a row that IS that inquiry. It keeps its own row on the
        # requirements screen, where naming what is missing is the useful thing to say.
        if i["code"] in rules.DERIVED:
            continue
        code = rules._asked_code(i) or i["code"]
        if code in asked:
            # When it went out and who sent it: a chase list is answered by picking up the phone,
            # and the person who asked is who the driver will have spoken to.
            waiting["driver"].append(card(i, {
                "asked": days(asked[code]),
                "askedon": asked[code].get("senton") or asked[code].get("createdon"),
                "askedby": asked[code].get("askedby")}))
        elif code in ordered or (i["code"] == "ROAD_TEST" and outside) \
                or (i["evidencesource"] == "employerhistory" and employers_out):
            waiting["outside"].append(card(i))
        else:
            waiting["office"].append(card(i))

    # 3. Read by nobody here. Invisible everywhere else, and the one list entirely within the
    #    office's own power to clear.
    unread = [card(i) for i in live if i["status"] == "review"]

    # 4. Expiring soon means something different before hire: not "this lapses", but "this would
    #    need renewing almost immediately after taking them on".
    soon = sorted([{**card(i), "expireson": i["expireson"],
                    "days": (i["expireson"] - today).days}
                   for i in live
                   if i.get("expireson") and today <= i["expireson"] <= today + timedelta(days=30)],
                  key=lambda x: x["expireson"])

    # Everything this driver must qualify with that CAN go out of date - whether or not anything
    # is on file for it yet. A document with a life is a different kind of obligation from one that
    # is done once: it comes back round, and a file that shows only what is outstanding today has
    # nothing to say about what will be outstanding next month.
    tracked = []
    for i in live:
        if (i.get("recurrence") or "once") not in ("days", "ondocument"):
            continue
        ends = i.get("expireson")
        # On file, and nothing about it is being tracked. `ondocument` means "it lasts as long as
        # the document says", and some documents say nothing: a wheelchair securement certificate
        # is trained to proficiency with no interval behind it, and its type sets no age limit
        # either. Listed here it is permanent furniture - no date, no countdown, nothing that will
        # ever change - on a panel whose entire claim is that these things go out of date. It
        # comes back the moment anybody records an expiry for it.
        if i.get("on") and not ends:
            continue
        if not i.get("on") and not ends:
            band = "none"
        elif not ends:
            band = "current"
        elif ends < today:
            band = "expired"
        elif ends <= today + timedelta(days=30):
            band = "expiring"
        else:
            band = "current"
        # A licence runs out; a screening falls due again. The same date means two different things
        # and is read by two different people, so the record says which kind it is and when it was
        # last done - "expires" against a recheck interval is the wrong word for the right date.
        tracked.append({"code": i["code"], "name": i["name"], "expireson": ends, "band": band,
                        "recurs": "interval" if (i.get("recurrence") == "days") else "document",
                        "on": i.get("on"),
                        "days": (ends - today).days if ends else None})
    tracked.sort(key=lambda x: ({"expired": 0, "expiring": 1, "none": 2, "current": 3}[x["band"]],
                                x["expireson"] or date.max))

    app_ = row(conn, """
        SELECT status, startedon, submittedon FROM driverapplications
        WHERE driverid = :d AND accountid = :a ORDER BY startedon DESC LIMIT 1
    """, d=driverid, a=acct)

    return {
        "driver": {"name": f'{driver["firstname"]} {driver["lastname"]}'.strip().title(),
                   "status": driver["status"]},
        "application": ({"status": app_["status"],
                         "startedon": app_["startedon"], "submittedon": app_["submittedon"],
                         "age": (today - (app_["submittedon"] or app_["startedon"]).date()).days}
                        if app_ else None),
        "adverse": adverse,
        "waiting": waiting,
        "unread": unread,
        "expiring": soon,
        "tracked": tracked,
        # Complete means on file and in date today. "Expiring" is in date - it is a renewal the
        # validity panel is there to carry, not an outstanding requirement, and counting it as
        # outstanding leaves a number nothing on this screen can be traced back to.
        "counts": {"required": len([i for i in live if i["status"] not in DONE_STATUS]),
                   "satisfied": len([i for i in live if i["status"] in DONE_STATUS]),
                   "total": len(live), "later": later,
                   # The two questions, counted apart, because they are not the same question and
                   # answering them with one number is what made the remainder untraceable. What
                   # stands between the company and taking somebody on is the paperwork of
                   # employment; what stands between them and a vehicle is 382.301, 391.31 and
                   # 391.43, and a company may well do the first while the second is outstanding.
                   "hire": _tally([i for i in live
                                   if (i["duestage"] or "prehire") == "prehire"]),
                   # Everything standing between this driver and a vehicle, which is not only the
                   # predrive stage: a hard stop owed at any stage stops them just the same, and a
                   # reading that counted only one of the two would show a full ring beside a red
                   # line saying the driver may not drive.
                   "drive": _tally([i for i in items if i["applies"] is True
                                    and ((i["duestage"] or "prehire") == "predrive"
                                         or i.get("gate") == "hardstop")
                                    and _owed_now(i, bool(driver.get("hiredon"))
                                                  or driver["status"] in ("hired", "inactive"))])},
        # Whether they may be put in a vehicle today, by the gate that already decides it for a
        # hired driver. Said here so the pre-hire screen and the roster read one answer.
        "stops": gate["stops"],
        # Collapsed on screen: worth being able to check why something is not being asked for when
        # a broker questions the file.
        "notapplicable": [{"code": i["code"], "name": i["name"], "why": i["why"]}
                          for i in items if i["applies"] is False],
        "candrive": gate["candrive"],
    }


@router.get("/drivers/{driverid}/overview")
def driver_overview(driverid: str, user: dict = Depends(current_user),
                    conn: Connection = Depends(get_conn)):
    """One screen's worth of what somebody needs to know about this driver this morning.

    Nothing is computed here that is not computed elsewhere - this reads the same engine the
    requirements list reads and sorts it into the four questions an office actually asks: what is
    waiting on me, what stops this driver, what is about to run out, and what has been happening.
    """
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    driver = _driver_for_rules(conn, acct, driverid)
    # A dashboard is for somebody who drives. An applicant's screen is their application and the
    # requirements standing between them and being hired - asking "what expires in 30 days" about
    # a person who has never driven for this company is a question with no useful answer.
    if not (driver.get("hiredon") or driver["status"] in ("hired", "inactive")):
        raise HTTPException(409, "This driver has not been hired yet")
    gathered = factset.assemble(conn, acct, driverid)
    items = rules.for_driver(conn, acct, driverid, gathered["facts"])
    today = localnow(user["timezone"]).date()
    gate = _gate(conn, acct, driverid, items, gathered["facts"])

    # On file and unread. The office's own work, and the one gap nobody notices: a document that
    # arrived and was never looked at reads like a document that was.
    review = [{"code": i["code"], "name": i["name"], "why": i["why"], "on": i["on"]}
              for i in items if i["status"] == "review"]

    # Running out, not yet run out. Ordered by the day it happens, because that is the order the
    # work has to be done in.
    soon = sorted(
        [{"code": i["code"], "name": i["name"], "expireson": i["expireson"],
          "days": (i["expireson"] - today).days}
         for i in items
         if i.get("expireson") and today <= i["expireson"] <= today + timedelta(days=HORIZON_DAYS)],
        key=lambda x: x["expireson"])

    return {
        "driver": {"name": f'{driver["firstname"]} {driver["lastname"]}'.strip().title(),
                   "status": driver["status"], "hiredon": driver["hiredon"]},
        "review": review,
        # What stops this driver today, which is narrower than what is missing from their file.
        "disqualifications": gate["stops"],
        "candrive": gate["candrive"],
        "dotdrugalcohol": gate["dotdrugalcohol"],
        "clearinghouse": gate["clearinghouse"],
        "deficiencies": gate["deficiencies"],
        "upcoming": soon,
        "horizon": HORIZON_DAYS,
        # The same history the activity tab shows, cut to what fits on a dashboard.
        "activity": application_activity(driverid, user, conn)["events"][:10],
    }


def _alternate_open(conn: Connection, accountid: str, driverid: str, rule: dict) -> bool:
    """Whether this rule may currently be answered by the evidence another one holds.

    It is a condition the company has to have met and said it has met, not a default - see
    migration 125 and F.A.C. 14-90.0041(1)(b)."""
    if not rule.get("alternatesource"):
        return False
    gathered = factset.assemble(conn, accountid, driverid)
    return rules.applies(rules.condition(rule["alternatewhen"]), gathered["facts"]) is True


@router.get("/drivers/{driverid}/requirements/{code}")
def requirement_detail(driverid: str, code: str, user: dict = Depends(current_user),
                       conn: Connection = Depends(get_conn)):
    """One requirement, everything held against it, and what would answer it.

    The client does not need to know which rule this is to show the right form - the rule says what
    kind of evidence it takes and where that evidence lives, and the form follows from that. It is
    the same reason the engine is data: a new requirement about a new report is a row, and the
    screen for it already exists."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    rule = row(conn, """
        SELECT recordid, code, name, description, authority, citation, evidencekind, evidencesource,
               -- `origin` decides whether a record can be "read" at all. Left out of this query,
               -- needs_reading() fell back to its default of "came from outside", so a record
               -- the office typed in itself - the day a driver went into the random pool - was
               -- offered a Mark As Reviewed button, against a rule whose origin is `office`.
               origin,
               alternatesource, alternatewhen, reviewrequired, determination, recurrence,
               recurrencedays, duestage, blocking, retentionrule, sensitivity
        FROM compliancerules WHERE code = :c AND subject = 'driver' AND effectiveto IS NULL
          AND (accountid IS NULL OR accountid = :a) LIMIT 1
    """, c=code, a=acct)
    if not rule:
        raise HTTPException(404, "No such requirement")

    kind, _, which = (rule["evidencesource"] or "").partition(":")
    # What the form needs to file one: a credential type to write against, or the doctype to ask
    # the driver to sign.
    # `category` comes with it because a training record is asked for differently from a licence:
    # it has somebody who gave it, and who that was is part of the record.
    ctype = row(conn, "SELECT recordid, name, category, requirestesting, defaultvaliddays "
                      "FROM credentialtypes "
                      "WHERE code = :c AND active = 1", c=which) if kind == "credential" else None
    signed = None
    if kind == "signature":
        signed = row(conn, """
            SELECT DATE(signedon) AS signedon FROM documentsignatures
            WHERE accountid = :a AND ownertype = 'driver' AND ownerid = :d AND doctype = :t
            ORDER BY signedon DESC LIMIT 1
        """, a=acct, d=driverid, t=which)
    return {
        "requirement": rule,
        "source": {"kind": kind or None, "which": which or None},
        # What the rule normally reads, plus anything filed straight against it - a paper copy of a
        # form TripProof does not generate answers the rule just as well as one it does.
        # Where another rule's evidence may answer this one, what is held for it belongs here too -
        # otherwise the list says the requirement is met and the screen behind it shows nothing.
        "records": _with_readings(
            conn, acct, driverid, rule,
            rules.history(conn, acct, driverid, rule["evidencesource"])
            + rules.filed_history(conn, acct, driverid, rule["recordid"])
            + _answered(conn, acct, driverid, rule, kind)
            + (rules.history(conn, acct, driverid, rule["alternatesource"])
               if _alternate_open(conn, acct, driverid, rule) else [])),
        "signed": signed["signedon"] if signed else None,
        # A driving record belongs to the licence it was pulled on - a driver holding licences in
        # two states has two histories - so ordering or filing one has to say which.
        "licences": rows(conn, """
            SELECT recordid, number, state, active FROM driverlicenses
            WHERE accountid = :a AND driverid = :d ORDER BY active DESC, issued DESC
        """, a=acct, d=driverid) if kind == "mvr" else [],
        # A driving record pulled on a commercial licence carries the State's own answer about
        # medical qualification, and a record pulled on an ordinary one does not - so the form that
        # files it asks different questions, and this is what decides which.
        "cdl": (row(conn, "SELECT licenseclass FROM drivers WHERE recordid = :d AND accountid = :a",
                    d=driverid, a=acct) or {}).get("licenseclass", "").upper() in ("A", "B", "C"),
        "selfcerts": SELF_CERT, "medcertstatuses": MED_CERT_STATUS,
        "medvariances": MED_VARIANCE,
        # For a requirement answered by a determination: the question to put, and what was said.
        # A question only where somebody has to answer it. An age is READ, not asked, and offering
        # Yes and No for it invites a person to overrule arithmetic.
        "question": DRIVER_FACTS.get(which, (None, None))[1] if kind == "driverfact" else None,
        "reading": _fact_reading(conn, acct, driverid, which) if kind == "driverfact" else None,
        "answer": (row(conn, f"SELECT {DRIVER_FACTS[which][0]} AS a FROM drivers "
                             "WHERE recordid = :d AND accountid = :ac",
                       d=driverid, ac=acct) or {}).get("a")
                  if kind == "driverfact" and which in DRIVER_FACTS else None,
        # The paper certificate's expiry, so a discrepancy can name both dates rather than one.
        "card": (row(conn, """
            SELECT c.expireson FROM credentials c
              JOIN credentialtypes t ON t.recordid = c.credentialtypeid
            WHERE c.accountid = :a AND c.subject = 'driver' AND c.subjectid = :d
              AND t.code = 'DOT_MEDICAL_CARD' AND c.deleted IS NULL AND c.revokedon IS NULL
            ORDER BY c.issuedon DESC, c.added DESC LIMIT 1
        """, a=acct, d=driverid) or {}).get("expireson") if kind == "cdlismedical" else None,
        # Which licensing authorities this rule actually asks about, and how each one stands.
        # 49 CFR 391.23(a)(1) wants a record from every state the driver held a licence in over the
        # window, so the screen shows the states rather than one record and a silence.
        "coverage": mvrs.coverage(
            conn, acct, driverid, window=mvrs.HIRE_LOOKBACK,
            current_within=mvrs.horizon(rule),
        ) if kind == "mvr" else None,
        # Which of these the driver sent in and nobody has read yet. A requirement does not stand
        # on one of those, and the row says so rather than the office having to remember.
        "awaitingreview": sorted(rules.awaiting_review(conn, acct, driverid)),
        # Everything sent in from outside and unread, by what was asked for - the general form,
        # which covers a signature as well as an upload.
        "unreadasks": sorted(rules.answered_unread(conn, acct, driverid)),
        # Whether the driver sent anything documenting a disclosed violation. The questionnaire
        # itself is always a document once answered, so its existence proves nothing - what counts
        # is whether they attached the paperwork to it.
        "driverattached": _attached(conn, acct, driverid) if kind.startswith("applicationanswer")
                          else None,
        "credentialtype": ctype,
        # Only these two are sent away for; the rest are filed when they arrive.
        "orderable": kind in ("report", "mvr"),
        "signable": which if kind == "signature" and which in signing.SIGNABLE else None,
    }


class HireIn(BaseModel):
    confirm: bool = False
    note: str | None = None


@router.post("/drivers/{driverid}/hire")
def hire_driver(driverid: str, body: HireIn, request: Request, tasks: BackgroundTasks,
                user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Put the driver on the roster."""
    driver = _applicant(conn, user["accountid"], driverid)
    if driver["status"] in ("hired", "declined"):
        raise HTTPException(409, "This driver has already been decided on")
    run(conn, """
        UPDATE drivers SET status = 'hired', hiredon = COALESCE(hiredon, :today), updated = :now
        WHERE recordid = :id AND accountid = :a
    """, today=date.today(), now=utcnow(), id=driverid, a=user["accountid"])
    run(conn, """
        UPDATE driverapplications SET status = 'approved', reviewedby = :u, reviewedon = :now
        WHERE driverid = :id AND accountid = :a
    """, u=user["recordid"], now=utcnow(), id=driverid, a=user["accountid"])
    log(conn, user, "driverapplication-hired", "driver", driverid,
        {"note": (body.note or "").strip() or None}, ip=client_ip(request))

    # The two forms every new employee completes, sent the moment they are hired. One message and
    # one link: a new starter who gets two emails on their first day signs one and wonders what the
    # other was. The I-9 link goes out; the W-4 waits behind it and the page offers it next.
    # The I-9 and the W-4 go to everybody. The previous-7-days statement goes only to a driver
    # Part 395 reaches, because that is who it is about - 49 CFR 395.8(j)(2) asks the carrier to
    # obtain it before the driver begins work, so it travels with the rest of the first-day
    # paperwork rather than waiting for somebody to remember it on the morning of a dispatch.
    needs7 = _needs_prev7(conn, acct, driverid)
    packet = ["I9", "W4"] + (["PREV7_ONDUTY"] if needs7 else [])
    sent = None
    for doctype in packet:
        already = row(conn, """
            SELECT recordid FROM signingrequests
            WHERE accountid = :a AND driverid = :d AND doctype = :t
              AND signedon IS NULL AND cancelledon IS NULL AND expireson > :now
        """, a=user["accountid"], d=driverid, t=doctype, now=utcnow())
        if already:
            continue
        made = signing.create(conn, user["accountid"], driverid, doctype, user["recordid"])
        sent = sent or made
    company = row(conn, "SELECT name FROM accounts WHERE recordid = :a",
                  a=user["accountid"])["name"]
    if sent and driver.get("email"):
        run(conn, "UPDATE signingrequests SET sentto = :to, senton = :now "
                  "WHERE accountid = :a AND driverid = :d AND doctype IN "
                  "('I9', 'W4', 'PREV7_ONDUTY') AND signedon IS NULL",
            to=driver["email"], now=utcnow(), a=user["accountid"], d=driverid)
        subject, html, text = emails.welcome_aboard(
            name=f'{driver["firstname"]} {driver["lastname"]}'.strip(), accountname=company,
            link=sent["link"], days=sent["days"])
        tasks.add_task(mailer.send, driver["email"], subject, html, text)
    saved(conn)
    return {"ok": True, "status": "hired"}


@router.post("/drivers/{driverid}/deactivate")
def deactivate_driver(driverid: str, request: Request, user: dict = Depends(editor),
                      conn: Connection = Depends(get_conn)):
    """Take the driver off the roster.

    The opposite of hiring, and the one decision still open on somebody already on it. The hire
    date stays where it is - when they started is a fact, and a driver who comes back is the same
    person with the same qualification history behind them - and the day they came off is stamped
    beside it.

    Anything still out with them is left alone. A licence that expires next month still expires
    next month, and an I-9 waiting to be read is still waiting: taking somebody off the roster
    answers no question about their paperwork, and quietly closing those would lose the record of
    what was outstanding on the day they left.
    """
    driver = _applicant(conn, user["accountid"], driverid)
    if driver["status"] != "hired":
        raise HTTPException(409, "This driver is not on the roster")
    run(conn, """
        UPDATE drivers SET status = 'inactive', terminatedon = COALESCE(terminatedon, :today),
                           updated = :now
        WHERE recordid = :id AND accountid = :a
    """, today=date.today(), now=utcnow(), id=driverid, a=user["accountid"])
    # Off the roster is out of the pool. 382.305 reaches drivers who perform safety-sensitive
    # functions; somebody who has stopped is not one, and leaving them in both inflates the
    # denominator every test rate is computed against and offers their name at the next draw.
    randompool.reconcile(conn, user["accountid"], driverid)
    log(conn, user, "driver-deactivated", "driver", driverid,
        {"terminatedon": str(date.today())}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "status": "inactive", "evaluation": evaluation}


def _needs_prev7(conn: Connection, acct: str, driverid: str) -> bool:
    """Whether 49 CFR 395.8(j)(2) reaches this driver.

    Asked of the engine rather than worked out again here: the rule already carries the
    condition, and a second copy of it in the hire routine is how the packet comes to disagree
    with the requirement it is meant to answer."""
    got = {r["code"]: r for r in rules.for_driver(
        conn, acct, driverid, factset.assemble(conn, acct, driverid)["facts"])}
    return (got.get("PREV7_ONDUTY") or {}).get("applies") is True


def _tell_driver_to_correct(*, email: str, name: str, accountname: str, link: str,
                            note: str | None) -> None:
    """Sent after the response, so it is handed plain values rather than the request's connection."""
    subject, html, text = emails.application_returned(name=name, accountname=accountname, link=link, note=note)
    mailer.send(email, subject, html, text)


class RandomPoolIn(BaseModel):
    on: date | None = None                # the day they went in; None takes them out again


@router.put("/drivers/{driverid}/random-pool")
def set_random_pool(driverid: str, body: RandomPoolIn, request: Request,
                    user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Put this driver in the random testing pool, or take them out - 49 CFR 382.305.

    Its own endpoint rather than a field on the whole-driver update, because the requirement is
    answered from the requirement, and a dialog that holds one date must not be made to send back
    an entire driver record it never loaded. That is how a screen with one field quietly blanks
    an address.
    """
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    if body.on:
        randompool.join(conn, acct, driverid, body.on, by=user["recordid"])
    else:
        # Taking somebody out CLOSES the spell rather than erasing it. The row is what answers
        # "who was in the pool on the day of that draw", which is the question a 382.305 rate
        # audit asks and the one a single cleared date could never answer again.
        randompool.leave(conn, acct, driverid, localnow(user["timezone"]).date())
    held = randompool.standing(conn, acct, driverid)
    log(conn, user, "randompool", "driver", driverid,
        {"joinedon": str(body.on) if body.on else None,
         "left": not body.on}, ip=client_ip(request))
    saved(conn)
    return {"joinedon": str(held["joinedon"]) if held else None,
            "leftpoolon": str(held["leftpoolon"]) if held and held["leftpoolon"] else None}


@router.put("/drivers/{driverid}")
def update_driver(driverid: str, body: DriverIn, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    _driver_phone(body)
    # An application is the driver's own statement, and it is signed. Nobody edits it from this side
    # while it is in their hands or waiting to be read; decide on it first.
    standing = row(conn, "SELECT status FROM drivers WHERE recordid = :id AND accountid = :a AND deleted IS NULL",
                   id=driverid, a=user["accountid"])
    if standing and standing["status"] in APPLYING:
        raise HTTPException(409, "This driver is still an applicant. Their application cannot be edited here.")
    r = run(conn, """
        UPDATE drivers SET externalid = :ext, firstname = :f, lastname = :l, dob = :dob, licensenumber = :lic,
               licensestate = :ls, licensesince = :lsince, email = :em, phone = :ph,
               emergencyname = :en, emergencyphone = :ep, hiredon = :h, terminatedon = :t,
               address1 = :a1, address2 = :a2, city = :city, state = :st, zip = :zip,
               operation = :operation, chapter1490 = :ch1490, datprogram = :dat,
               endorsementsneeded = :needs, englishproficient = :english, stub = 0,
               updated = :now
        WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=driverid, a=user["accountid"], ext=body.externalid or None, f=body.firstname, l=body.lastname, dob=body.dob,
        lic=body.licensenumber, ls=body.licensestate, lsince=body.licensesince, em=body.email, ph=body.phone,
        en=(body.emergencyname or None), ep=(body.emergencyphone or None),
        h=body.hiredon, t=body.terminatedon, a1=body.address1, a2=body.address2, city=body.city,
        st=(body.state or "").upper()[:2] or None, zip=body.zip,
        operation=body.operation if body.operation in OPERATION else "noncmv",
        ch1490=int(bool(body.chapter1490)),
        # Kept as the letters themselves, in one order, so "P, S" and "sp" are one answer.
        needs="".join(rules.ENDORSEMENTS(body.endorsementsneeded)) or None,
        english=None if body.englishproficient is None else int(body.englishproficient),
        dat=body.datprogram if body.datprogram in eligibility.PROGRAMMES else None,
        now=utcnow())
    if not r.rowcount:
        raise HTTPException(404, "Driver not found")
    # A termination date typed in here, or a move to work Part 382 does not reach, takes the
    # driver out of the random pool for the same reason deactivating them does.
    randompool.reconcile(conn, user["accountid"], driverid)
    log(conn, user, "update", "driver", driverid, body.model_dump(mode="json"))
    # Date of birth and first-licensed date feed the age and years-licensed rules.
    return {"ok": True, "evaluation": _reevaluate_subject(conn, user, "driver", driverid)}


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
        # What stops the vehicle: a defect reported and not put right. 49 CFR 396.11(c).
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
        v["licence"] = vehicleclass.licence_for(v)
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
        v["licence"] = vehicleclass.licence_for(v)
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


# ------------------------------------------------------------------------------------------------
# Company profile (Settings -> Company). Owners and admins edit it; moving the company re-checks
# every trip, since state, county and city decide which rules apply.
# ------------------------------------------------------------------------------------------------

class CompanyIn(BaseModel):
    name: str | None = None
    dba: str | None = None
    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    county: str | None = None
    state: str | None = None
    zip: str | None = None
    phone: str | None = None
    fax: str | None = None
    email: str | None = None
    supportemail: str | None = None
    billingemail: str | None = None
    ein: str | None = None
    # FMCSA's identifiers. The USDOT number is not decoration: 49 CFR 390.19(b) reads the biennial
    # update's month off its last digit and the year off the digit before it.
    usdot: str | None = None
    mcnumber: str | None = None
    medicaidid: str | None = None
    npi: str | None = None


@router.get("/company")
def get_company(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    return row(conn, f"SELECT accountnumber, timezone, {', '.join(PROFILE_FIELDS)} "
                     "FROM accounts WHERE recordid = :a", a=user["accountid"])


@router.put("/company")
def put_company(body: CompanyIn, request: Request, user: dict = Depends(account_admin), conn: Connection = Depends(get_conn)):
    before = row(conn, "SELECT state, county, city FROM accounts WHERE recordid = :a", a=user["accountid"])
    fields = clean_profile(body.model_dump(exclude_unset=True))
    if "state" in fields and not fields["state"]:
        raise HTTPException(400, "State is required")
    if fields:
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        run(conn, f"UPDATE accounts SET {sets}, updated = :now WHERE recordid = :a", now=utcnow(), a=user["accountid"], **fields)
    log(conn, user, "update-company", "account", user["accountid"], fields, ip=client_ip(request))
    moved = any(k in fields and (fields[k] or "").lower() != (before[k] or "").lower() for k in ("state", "county", "city"))
    return {"ok": True, "evaluation": evaluate(conn, user["accountid"], userid=user["recordid"], reason="company moved") if moved else None}


# ------------------------------------------------------------------------------------------------
# Company credentials (COIs, business tax receipt)
# ------------------------------------------------------------------------------------------------

@router.get("/company/credentials")
def company_credentials(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    today = localnow(user["timezone"])
    return _mark_replaced([_status_today(c, today) for c in _credentials(conn, user["accountid"], "company", user["accountid"])])


# ------------------------------------------------------------------------------------------------
# Credentials
# ------------------------------------------------------------------------------------------------

def _subject_exists(conn: Connection, acct: str, subject: str, subjectid: str) -> bool:
    if subject == "company":
        return subjectid == acct
    table = "drivers" if subject == "driver" else "vehicles"
    return bool(row(conn, f"SELECT 1 AS x FROM {table} WHERE recordid = :id AND accountid = :a AND deleted IS NULL",
                    id=subjectid, a=acct))


@router.post("/credentials")
async def create_credential(
    request: Request,
    credentialtypeid: str = Form(...),
    subjectid: str = Form(...),
    issuedon: date | None = Form(None),
    expireson: date | None = Form(None),
    exempt: bool = Form(False),
    number: str | None = Form(None),
    issuer: str | None = Form(None),
    # Training that has to be demonstrated carries a second date: the day the skill was shown,
    # and who watched it being shown. See F.A.C. 14-90.004(3)(d).
    testedon: date | None = Form(None),
    testedby: str | None = Form(None),
    amount: float | None = Form(None),
    notes: str | None = Form(None),
    supersedes: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    acct = user["accountid"]
    ctype = row(conn, "SELECT recordid, subject, hasamount FROM credentialtypes WHERE recordid = :id AND active = 1",
                id=credentialtypeid)
    if not ctype:
        raise HTTPException(400, "Unknown credential type")
    if ctype["subject"] == "company":
        subjectid = acct
    if not _subject_exists(conn, acct, ctype["subject"], subjectid):
        raise HTTPException(404, f"{ctype['subject'].title()} not found")
    # A driver operating under an exemption has no certificate to date, so the record is dated the
    # day the office recorded it. Everything else needs the date the document itself carries.
    if issuedon is None:
        if not exempt:
            raise HTTPException(400, "The date it was issued is required")
        issuedon = localnow(user["timezone"]).date()
    if expireson and expireson < issuedon:
        raise HTTPException(400, "Expiration date is before the issue date")

    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "File is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)

    if supersedes and not row(conn, "SELECT 1 AS x FROM credentials WHERE recordid = :id AND accountid = :a",
                              id=supersedes, a=acct):
        supersedes = None
    cid = newid()
    run(conn, """
        INSERT INTO credentials (recordid, accountid, credentialtypeid, subject, subjectid, documentid, number, issuer, amount,
                                 issuedon, testedon, testedby, expireson, exempt, supersedes, notes, enteredby)
        VALUES (:id, :a, :t, :s, :sid, :doc, :num, :iss, :amt, :io, :to, :tby, :eo, :ex, :sup, :notes, :u)
    """, id=cid, a=acct, t=credentialtypeid, s=ctype["subject"], sid=subjectid, doc=documentid, num=number,
        iss=issuer, amt=amount if ctype["hasamount"] else None, io=issuedon,
        to=testedon, tby=(testedby or None), eo=expireson,
        ex=1 if exempt else 0, sup=supersedes, notes=notes, u=user["recordid"])
    # Somebody in this office put it here, so somebody in this office has read it. A medical
    # certificate is made by an examiner and a training certificate by a trainer - both come from
    # outside - but whoever typed the dates off them was holding the paper, and asking them to go
    # back afterwards and tick "reviewed" on a thing they have just read is asking twice.
    if ctype["subject"] == "driver":
        _filed_here(conn, acct, subjectid, "credentials", cid, user["recordid"])
    log(conn, user, "create", "credential", cid, {"type": credentialtypeid, "subject": ctype["subject"],
                                                  "subjectid": subjectid, "issuedon": issuedon, "expireson": expireson},
        ip=client_ip(request))
    return {"recordid": cid, "documentid": documentid,
            "evaluation": _reevaluate_subject(conn, user, ctype["subject"], subjectid)}


class RevokeIn(BaseModel):
    revokedon: datetime
    reason: str


@router.post("/credentials/{credentialid}/revoke")
def revoke_credential(credentialid: str, body: RevokeIn, user: dict = Depends(editor),
                      conn: Connection = Depends(get_conn)):
    c = row(conn, "SELECT subject, subjectid, revokedon FROM credentials WHERE recordid = :id AND accountid = :a AND deleted IS NULL",
            id=credentialid, a=user["accountid"])
    if not c:
        raise HTTPException(404, "Credential not found")
    if c["revokedon"]:
        raise HTTPException(409, "Already revoked")
    run(conn, "UPDATE credentials SET revokedon = :r, revokereason = :why, updated = :now WHERE recordid = :id",
        r=body.revokedon, why=body.reason[:255], now=utcnow(), id=credentialid)
    log(conn, user, "revoke", "credential", credentialid, body.model_dump(mode="json"))
    return {"ok": True, "evaluation": _reevaluate_subject(conn, user, c["subject"], c["subjectid"])}


@router.delete("/credentials/{credentialid}")
def delete_credential(credentialid: str, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """For data-entry mistakes only. A renewal is a new credential, never an edit or a delete."""
    c = row(conn, "SELECT subject, subjectid FROM credentials WHERE recordid = :id AND accountid = :a AND deleted IS NULL",
            id=credentialid, a=user["accountid"])
    if not c:
        raise HTTPException(404, "Credential not found")
    run(conn, "UPDATE credentials SET deleted = :now WHERE recordid = :id", now=utcnow(), id=credentialid)
    log(conn, user, "delete", "credential", credentialid)
    return {"ok": True, "evaluation": _reevaluate_subject(conn, user, c["subject"], c["subjectid"])}


@router.get("/documents/{documentid}")
def download_document(documentid: str, request: Request, user: dict = Depends(current_user),
                      conn: Connection = Depends(get_conn)):
    d = row(conn, "SELECT filename, mimetype, storagekey FROM documents WHERE recordid = :id AND accountid = :a AND deleted IS NULL",
            id=documentid, a=user["accountid"])
    if not d:
        raise HTTPException(404, "Document not found")
    log(conn, user, "view", "document", documentid, ip=client_ip(request))
    try:
        blob = storage.get(d["storagekey"])
    except storage.Missing:
        raise HTTPException(410, "That file is no longer stored")
    return Response(blob, media_type=d["mimetype"],
                    headers={"Content-Disposition": f'inline; filename="{d["filename"]}"'})


# -------------------------------------------------------------------------------------------
# How this company takes a card for a private-pay trip.
#
# Its own merchant account, not TripProof's. The keys belong to the company and never come
# back out: what a read returns is whether each secret is set and its last four characters.
# -------------------------------------------------------------------------------------------

class GatewayConfigIn(BaseModel):
    mode: str = "test"
    values: dict[str, str] = {}


def _own_keys_only(user: dict):
    """TripProof staff configure nobody's gateway.

    A launched session is us standing in the customer's office, not us being them - the same
    line already drawn around their users. Merchant credentials are the sharpest edge of it:
    staff who can write a key can point a company's takings at another account, and no
    support task needs that.
    """
    if user.get("platformrole"):
        raise HTTPException(403, "TripProof staff cannot configure a customer's payment "
                                 "gateway - the company holds its own merchant keys")


@router.get("/company/gateways")
def payment_gateways(user: dict = Depends(account_admin), conn: Connection = Depends(get_conn)):
    """What is on offer, what this company has set up, and which one it uses."""
    return gateways.summary(conn, user["accountid"])


@router.put("/company/gateways/{code}")
def configure_gateway(code: str, body: GatewayConfigIn, request: Request,
                      user: dict = Depends(account_admin),
                      conn: Connection = Depends(get_conn)):
    _own_keys_only(user)
    if code not in gateways.ADAPTERS:
        raise HTTPException(404, "No such payment gateway")
    if not any(g["code"] == code for g in gateways.offered(conn)):
        raise HTTPException(409, f"{gateways.describe(code)} is not available")
    gateways.save(conn, user["accountid"], user["recordid"], code, body.model_dump())
    # The field NAMES are logged, never a value - enough to answer "what changed on Tuesday"
    # without the log becoming the place the keys leak from.
    log(conn, user, "gateway-configured", "company", user["accountid"],
        {"gateway": code, "mode": body.mode, "fields": sorted(body.values or {})},
        ip=client_ip(request))
    saved(conn)
    return gateways.summary(conn, user["accountid"])


@router.post("/company/gateways/{code}/use")
def use_gateway(code: str, request: Request, user: dict = Depends(account_admin),
                conn: Connection = Depends(get_conn)):
    """Take private payments through this one."""
    _own_keys_only(user)
    held = next((g for g in gateways.configured(conn, user["accountid"]) if g["code"] == code),
                None)
    if not held:
        raise HTTPException(404, "That gateway is not set up yet")
    # Gated here rather than warned about afterwards: a gateway missing a key cannot take a
    # payment, so it is not offered as the one that will.
    if not held["ready"]:
        raise HTTPException(409, f"{gateways.describe(code)} is missing something it needs. "
                                 "Fill the rest in first.")
    gateways.use(conn, user["accountid"], code)
    log(conn, user, "gateway-chosen", "company", user["accountid"], {"gateway": code},
        ip=client_ip(request))
    saved(conn)
    return gateways.summary(conn, user["accountid"])


@router.delete("/company/gateways/{code}")
def forget_gateway(code: str, request: Request, user: dict = Depends(account_admin),
                   conn: Connection = Depends(get_conn)):
    """Remove it, keys and all."""
    _own_keys_only(user)
    if not gateways.forget(conn, user["accountid"], code):
        raise HTTPException(404, "That gateway is not set up")
    log(conn, user, "gateway-removed", "company", user["accountid"], {"gateway": code},
        ip=client_ip(request))
    saved(conn)
    return gateways.summary(conn, user["accountid"])
