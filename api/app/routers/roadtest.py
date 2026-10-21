"""Section 2 of the I-9, The road test - moved out of routers/vault.py, which grew too large to work in safely.

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
    _tell_driver_to_correct,
    driver_files,
)

router = APIRouter(prefix="/api", tags=["vault"])


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
    # The certifier's own signature, against the file they certified. Filed against the DRIVER,
    # whose document it is - ownertype/ownerid say whose record a signature belongs to, not who
    # put their name to it, and that is on the signature itself. Hashed on the FILE, as the
    # employee's was: there is no text behind an official form to hash.
    signatures.sign(conn, acct, sig["recordid"], "I9_SECTION2", driverid, "", ownertype="driver",
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


@router.get("/drivers/{driverid}/signed/{doctype}/pdf")
def driver_signed_document_pdf(driverid: str, doctype: str, request: Request,
                               user: dict = Depends(current_user),
                               conn: Connection = Depends(get_conn)):
    """The same signed document, drawn as a PDF.

    Rendered here rather than shown as a page of HTML, for two reasons that are really one. A
    document read on screen and the same document printed have to be the same document - a sheet
    that reflows to the window is not what anybody will put in front of an auditor - and the PDF
    is already how this file leaves the building, in the audit packet and in the driver's own
    copy. Reading it as a PDF means reading the thing that will be sent.

    Nothing new is drawn: `to_pdf` lays out the very HTML and stylesheet the portal shows, with
    the signing faces carried in as data so the renderer needs nothing from the web."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    if doctype.startswith("ANNUAL_REVIEW:"):
        view = annualreview.sheet(conn, acct, driverid, doctype.split(":", 1)[1])
    else:
        view = applicationview.signed_document(conn, acct, driverid, doctype)
    if not view:
        raise HTTPException(404, "This driver has not signed that")
    # A form signed on the government's own paper is a stored file after all, and the stored file
    # is the evidence. Rebuilding our own version of it would be drawing a picture of the record.
    if view.get("documentid"):
        doc = row(conn, "SELECT filename, mimetype, storagekey FROM documents "
                        "WHERE recordid = :id AND accountid = :a", id=view["documentid"], a=acct)
        if doc:
            try:
                blob = storage.get(doc["storagekey"])
            except storage.Missing:
                raise HTTPException(404, "That file is missing from storage") from None
            return Response(content=blob, media_type=doc["mimetype"] or "application/pdf",
                            headers={"Content-Disposition":
                                     f'inline; filename="{doc["filename"]}"'})
    pdf = applicationview.to_pdf(view, applicationview.signature_css())
    log(conn, user, "view", "signeddocument", driverid, {"doctype": doctype, "as": "pdf"},
        ip=client_ip(request))
    saved(conn)
    name = f"{doctype.lower().replace(':', '-')}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}"'})


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
    # Into pending means screened against OIG and SAM.gov, there and then. Inside the same save:
    # where a list cannot be had, the move does not happen, so nobody reaches pending unscreened.
    if driverstatus == "pending" and driver["status"] != "pending":
        try:
            screening.screen_now(conn, driverid)
        except Exception as e:
            raise HTTPException(503, "The exclusion screening could not be run, so this driver "
                                     f"was not moved to Pending. Try again shortly. ({e})") from None
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
