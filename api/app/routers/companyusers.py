"""The company's own logins - moved out of routers/vault.py, which grew too large to work in safely.

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
    COMPANY_ROLES,
)

router = APIRouter(prefix="/api", tags=["vault"])


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
                   AND d.doctype = 'SUPERVISOR_TRAINING_RECORD') AS trainingsignedon,
               -- The company appointments this person currently holds, each with the id of
               -- the appointment itself: ending one is done by its row, because who held a
               -- role and when is what an audit asks and a deleted row cannot answer it.
               (SELECT GROUP_CONCAT(CONCAT(r.role, ':', r.recordid))
                  FROM companyroles r
                 WHERE r.accountid = u.accountid AND r.userid = u.recordid
                   AND r.until IS NULL) AS heldroles
        FROM users u
        WHERE u.accountid = :a AND u.platformrole IS NULL
        ORDER BY u.deleted IS NOT NULL, u.name
    """, a=user["accountid"]),
        "me": user["recordid"],
        # The appointments a person can hold. One list, the same one the Company
        # Requirements screen appoints from.
        "companyroles": COMPANY_ROLES}


@router.post("/account/users")
def add_account_user(body: AccountUserIn, request: Request, tasks: BackgroundTasks,
                     user: dict = Depends(account_admin), conn: Connection = Depends(get_conn)):
    """Add a login and send its invitation. The login cannot be used until the invitation is.

    Open to TripProof staff working in the portal: adding someone cannot lock anybody out, which
    is what keeps them away from changing or closing the logins already there."""
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

    Nobody can close their own login or take away their own access, and the last owner can be
    neither demoted nor closed - by the company or by TripProof staff working in its portal. An
    account that locks out its last owner is an account that has to ring us."""
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


@router.get("/account/users/{userid}/documents")
def account_user_documents(userid: str, user: dict = Depends(account_admin),
                           conn: Connection = Depends(get_conn)):
    """What this person has put their own name to.

    Signatures BY a user, filed against them - at present the reasonable suspicion supervisor
    training record, which only they can sign. Read from the one place signatures live, so a
    document added later appears here without this endpoint being touched.
    """
    _their_user(conn, user["accountid"], userid)
    return {
        "labels": signatures.DOC_TYPES,
        "items": rows(conn, """
            SELECT d.recordid, d.doctype, d.signedon, s.signername, s.typedname
            FROM documentsignatures d JOIN signatures s ON s.recordid = d.signatureid
            WHERE d.accountid = :a AND d.ownertype = 'user' AND d.ownerid = :u
            ORDER BY d.signedon DESC
        """, a=user["accountid"], u=userid),
    }


@router.post("/account/users/{userid}/invite")
def invite_account_user(userid: str, request: Request, tasks: BackgroundTasks,
                        user: dict = Depends(account_admin), conn: Connection = Depends(get_conn)):
    """Email a link to set a password - a link nobody used, or a password nobody remembers.

    A login that has never set one gets an invitation; one that has gets a reset, which is a
    shorter-lived link and says the right thing in the mail. The same choice the admin side
    makes, because it is the same question. The current password keeps working until the
    link is used.
    """
    held = _their_user(conn, user["accountid"], userid)
    if held["deleted"]:
        raise HTTPException(400, "That login is closed")
    used = row(conn, """
        SELECT 1 AS x FROM activitylog
        WHERE userid = :u AND action IN ('password-set', 'login') LIMIT 1
    """, u=userid)
    purpose = "reset" if used else "invite"
    invited = admin._invite(conn, tasks, userid, purpose, user)
    log(conn, user, "account-invite-user", "user", userid, {"purpose": purpose},
        ip=client_ip(request))
    saved(conn)
    return {**invited, "purpose": purpose}


class ShiftIn(BaseModel):
    weekday: int
    startsat: str
    endsat: str


class ShiftsIn(BaseModel):
    shifts: list[ShiftIn] = []


@router.get("/drivers/{driverid}/shifts")
def driver_shifts(driverid: str, user: dict = Depends(current_user),
                  conn: Connection = Depends(get_conn)):
    """When this driver normally works."""
    acct = user["accountid"]
    if not row(conn, "SELECT 1 AS x FROM drivers WHERE recordid = :d AND accountid = :a "
                     "AND deleted IS NULL", d=driverid, a=acct):
        raise HTTPException(404, "No such driver")
    return {
        "days": dispatch.WEEKDAYS,
        "shifts": rows(conn, """
            SELECT recordid, weekday, startsat, endsat FROM drivershifts
            WHERE accountid = :a AND driverid = :d ORDER BY weekday, startsat
        """, a=acct, d=driverid),
    }


@router.put("/drivers/{driverid}/shifts")
def set_driver_shifts(driverid: str, body: ShiftsIn, request: Request,
                      user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Replace the week.

    Written whole rather than row by row: a working week is one thing a person decides, and
    patching days one at a time leaves a half-saved week if the second request never arrives."""
    acct = user["accountid"]
    if not row(conn, "SELECT 1 AS x FROM drivers WHERE recordid = :d AND accountid = :a "
                     "AND deleted IS NULL", d=driverid, a=acct):
        raise HTTPException(404, "No such driver")
    for s in body.shifts:
        if not 0 <= s.weekday <= 6:
            raise HTTPException(400, "That is not a day of the week")
        if not s.startsat or not s.endsat:
            raise HTTPException(400, "A shift needs a start and an end")
        if s.startsat == s.endsat:
            raise HTTPException(400, "A shift that starts and ends at the same moment is not one")
    run(conn, "DELETE FROM drivershifts WHERE accountid = :a AND driverid = :d", a=acct, d=driverid)
    for s in body.shifts:
        run(conn, """
            INSERT INTO drivershifts (recordid, accountid, driverid, weekday, startsat, endsat,
                                      added, addedby)
            VALUES (:id, :a, :d, :w, :s, :e, :now, :by)
        """, id=newid(), a=acct, d=driverid, w=s.weekday, s=s.startsat, e=s.endsat,
            now=utcnow(), by=user["recordid"])
    log(conn, user, "driver-shifts", "driver", driverid, {"days": len(body.shifts)},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/drivers/{driverid}/appaccess")
def invite_driver_to_the_app(driverid: str, request: Request, tasks: BackgroundTasks,
                             user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Email this driver a link to set a password for the driver app.

    An invitation the first time, a reset after that - the same distinction the office logins
    make, because it is the same question and the mail has to say the right thing. The link goes
    to the app, not to the office sign-in."""
    acct = user["accountid"]
    held = row(conn, """
        SELECT recordid, firstname, lastname, email, passwordhash, appaccess
        FROM drivers WHERE recordid = :d AND accountid = :a AND deleted IS NULL
    """, d=driverid, a=acct)
    if not held:
        raise HTTPException(404, "No such driver")
    if not (held["email"] or "").strip():
        raise HTTPException(409, "This driver has no email address on file. Record one first.")
    # The address has to reach one person. Two driver records sharing it means neither can sign
    # in, so it is refused here rather than at the sign-in screen where nobody can fix it.
    shared = row(conn, """
        SELECT COUNT(*) AS n FROM drivers
        WHERE accountid = :a AND deleted IS NULL AND LOWER(email) = LOWER(:e)
    """, a=acct, e=held["email"])
    if int(shared["n"]) > 1:
        raise HTTPException(409, "That email address is on more than one driver record. Give this "
                                 "driver an address of their own first.")
    purpose = "reset" if held["passwordhash"] else "invite"
    link = invitations.issue_for_driver(conn, driverid, purpose, user["recordid"])
    emailed = invitations.email_configured()
    if emailed:
        tasks.add_task(invitations.deliver, purpose=purpose,
                       name=f'{held["firstname"]} {held["lastname"]}'.strip(),
                       email=held["email"], link=link, expires=invitations.expiry(purpose),
                       accountname=user["accountname"], staff=False, role=None,
                       invitedby=user["name"], tz=user.get("usertimezone"))
    log(conn, user, "driver-app-invite", "driver", driverid, {"purpose": purpose},
        ip=client_ip(request))
    saved(conn)
    # With no mail configured the link comes back to be passed on by hand, as everywhere else.
    return {"ok": True, "purpose": purpose, "emailed": emailed,
            "link": None if emailed else link}


@router.post("/drivers/{driverid}/appaccess/close")
def close_driver_app_access(driverid: str, request: Request, user: dict = Depends(editor),
                            conn: Connection = Depends(get_conn)):
    """Stop this driver signing in, without touching whether they may drive. Two questions."""
    acct = user["accountid"]
    r = run(conn, "UPDATE drivers SET appaccess = 0 WHERE recordid = :d AND accountid = :a "
                  "AND deleted IS NULL", d=driverid, a=acct)
    if not r.rowcount:
        raise HTTPException(404, "No such driver")
    log(conn, user, "driver-app-closed", "driver", driverid, {}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}
