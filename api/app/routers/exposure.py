"""The bloodborne pathogens exposure determination - moved out of routers/vault.py, which grew too large to work in safely.

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
    SUPERVISOR_BLANK,
    _policy_context,
    _with_stamp,
)

router = APIRouter(prefix="/api", tags=["vault"])


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
