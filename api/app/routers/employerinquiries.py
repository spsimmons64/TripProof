"""Previous employer safety performance history - moved out of routers/vault.py, which grew too large to work in safely.

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
    UploadRequestIn,
    _applicant,
    _filed_here,
    _reevaluate_subject,
)

router = APIRouter(prefix="/api", tags=["vault"])


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
