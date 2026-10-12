###################################################################################################
# The online driver application - /account/<number>/apply in the web app, no login.
#
# The applicant is identified by date of birth + Social Security number, checked against the drivers
# of that one account:
#   in application  → resume where they left off
#   pending         → "we have your application, it is being reviewed"
#   active/inactive → "you already work here, talk to the office"
#   no match        → start a new application
#
# The SSN is never stored in the clear: drivers.ssnhash is an HMAC under the PHI key, scoped to the
# account, and the number itself goes in the phi table. A session token carries the application id
# and is good for a few hours, so a half-finished form survives a closed browser.
#
# Ten steps. Steps 1-5 collect answers and files; 6-10 are documents, each signed with the adopted
# signature and stamped with the SHA-256 of the exact text shown.
###################################################################################################
import hashlib
import io
import json
import logging
import time
from collections import defaultdict, deque
from datetime import date, timedelta

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import (applicationview, documents, drivers, emails, events, i9, images, licensebarcode,
                 mailer, phi, signatures, storage)
from pypdf import PdfReader, PdfWriter

from app.activity import log
from app.config import settings
from app.db import get_conn, newid, row, rows, run, saved, utcnow
from app.security import client_ip

log_render = logging.getLogger("tripproof.driverapply")

router = APIRouter(prefix="/api/driverapply", tags=["driverapply"])

SESSION_HOURS = 6
MAX_UPLOAD = 15 * 1024 * 1024
STEPS = 9
# Form I-9 and Form W-4 are not asked for here: Section 1 of the I-9 may not be completed before a
# job offer has been accepted (see the form's own instruction, and 8 CFR 274a.2(b)(1)(i)(A)), and
# the W-4 belongs to the payroll that follows hiring. Both go out to the driver once they are hired.
STEP_DOCS = {3: "DRUG_POLICY", 4: "WORKPLACE_POLICY", 5: "PHI_ACK", 6: "CLEARINGHOUSE_CONSENT",
             7: "SAFETY_PERFORMANCE_CONSENT", 8: "FCRA_SUMMARY", 9: "FCRA_AUTH"}
# Asked only of a driver who will operate a commercial motor vehicle for the company.
CMV_DOCS = {"CLEARINGHOUSE_CONSENT", "SAFETY_PERFORMANCE_CONSENT"}
# Two of the documents belong to the company, not to us: the driver is shown the most recent copy
# the account has filed, and signs against that file. An account that has filed neither falls back
# to the wording we ship.
COMPANY_POLICIES = {"DRUG_POLICY": "DRUG_ALCOHOL_POLICY", "WORKPLACE_POLICY": "WORKPLACE_POLICY",
                    "PHI_ACK": "PHI_POLICY", "FCRA_AUTH": "FCRA_CONSENT"}
UPLOAD_KINDS = {"license_front", "license_back", "license_action", "medical_certificate", "i9_document"}
# Photographs of documents, or a PDF. Nothing else is worth accepting from a public form.
ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp", "image/heic",
                 "image/heif", "image/tiff", "image/bmp"}
MAGIC = ((b"%PDF-", "application/pdf"), (b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"),
         (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"), (b"BM", "image/bmp"),
         (b"II*\x00", "image/tiff"), (b"MM\x00*", "image/tiff"))


def _looks_like_a_document(data: bytes, declared: str) -> bool:
    """Trust the bytes, not the browser: a PDF or one of the common image formats. RIFF/WEBP and
    HEIF carry their marker a few bytes in, so those are checked separately."""
    if any(data.startswith(prefix) for prefix, _ in MAGIC):
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"hevc", b"mif1", b"msf1"):
        return True
    return False

# A brake on guessing. Only attempts that find nothing count: someone walking through Social
# Security numbers piles up misses, while an applicant who matches - starting, resuming, or being
# told their application is already in - is never held against them, however often they come back.
MISS_LIMIT = 20
MISS_WINDOW = 3600
_misses: dict[str, deque] = defaultdict(deque)


def _recent_misses(ip: str | None) -> deque:
    q = _misses[ip or "?"]
    now = time.monotonic()
    while q and now - q[0] > MISS_WINDOW:
        q.popleft()
    return q


def _too_many_misses(ip: str | None) -> bool:
    return len(_recent_misses(ip)) >= MISS_LIMIT


def _note_miss(ip: str | None) -> None:
    _recent_misses(ip).append(time.monotonic())


def _token(applicationid: str) -> str:
    now = utcnow()
    return jwt.encode({"app": applicationid, "iat": now, "exp": now + timedelta(hours=SESSION_HOURS)},
                      settings.jwt_secret, algorithm="HS256")


def session(request: Request, conn: Connection = Depends(get_conn)) -> dict:
    """The application this request belongs to, from the Bearer token the start step handed out."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "Not signed in")
    try:
        claims = jwt.decode(header[7:], settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Your application session has expired - start again to pick up where you left off")
    app_ = row(conn, """
        SELECT a.*, d.firstname, d.lastname, d.dob, d.status AS driverstatus, ac.name AS accountname
        FROM driverapplications a
        JOIN drivers d ON d.recordid = a.driverid
        JOIN accounts ac ON ac.recordid = a.accountid
        WHERE a.recordid = :id
    """, id=claims.get("app"))
    if not app_:
        raise HTTPException(401, "Application not found")
    return app_


def _public_account(conn: Connection, accountnumber: str) -> dict:
    acct = row(conn, """
        SELECT recordid, name, accountnumber FROM accounts
        WHERE accountnumber = :n AND platform = 0 AND deleted IS NULL AND status = 'active'
    """, n=accountnumber)
    if not acct:
        raise HTTPException(404, "That company is not taking applications")
    return acct


def _fullname(app_: dict) -> str:
    return f"{app_.get('firstname') or ''} {app_.get('lastname') or ''}".strip()


def _blanks(app_: dict) -> dict:
    """What the documents we ship put in their blanks: the company, the driver, and the licence the
    Clearinghouse consent is given under - the commercial one if the driver listed one."""
    data = json.loads(app_["data"] or "{}")
    licenses = ((data.get("steps") or {}).get("2") or {}).get("licenses") or []
    cdl = next((l for l in licenses if l.get("classification") in ("A", "B", "C")), None) or \
        (licenses[0] if licenses else {})
    return {"company": app_["accountname"], "fullname": _fullname(app_),
            "cdlstate": cdl.get("state", ""), "cdlnumber": cdl.get("number", ""),
            "dob": app_["dob"].strftime("%m/%d/%Y") if app_.get("dob") else ""}


def _company_policy(conn: Connection, accountid: str, doctype: str) -> dict | None:
    """The most recent copy of one of the company's own policies, or None if it has filed none."""
    code = COMPANY_POLICIES.get(doctype)
    if not code:
        return None
    return row(conn, """
        SELECT d.recordid, d.filename, d.mimetype, d.sha256, d.storagekey, c.issuedon, c.added
        FROM credentials c
        JOIN credentialtypes t ON t.recordid = c.credentialtypeid
        JOIN documents d ON d.recordid = c.documentid
        WHERE c.accountid = :a AND t.code = :code AND c.subject = 'company'
          AND c.revokedon IS NULL AND c.deleted IS NULL AND d.deleted IS NULL
        ORDER BY COALESCE(c.issuedon, DATE(c.added)) DESC, c.added DESC
        LIMIT 1
    """, a=accountid, code=code)


def _state(app_: dict) -> dict:
    return {"step": min(app_["step"], STEPS), "status": app_["status"], "accountname": app_["accountname"],
            "firstname": app_["firstname"], "lastname": app_["lastname"], "dob": str(app_["dob"]),
            "data": json.loads(app_["data"]) if app_["data"] else {}}


# ------------------------------------------------------------------------------------------------
# Getting in
# ------------------------------------------------------------------------------------------------

class StartIn(BaseModel):
    dob: date
    ssn: str
    firstname: str | None = None
    lastname: str | None = None


@router.get("/{accountnumber}")
def company(accountnumber: str, conn: Connection = Depends(get_conn)):
    """Who the applicant is applying to - all a stranger may see."""
    acct = _public_account(conn, accountnumber)
    return {"accountname": acct["name"], "accountnumber": acct["accountnumber"], "steps": STEPS}


@router.post("/{accountnumber}/start")
def start(accountnumber: str, body: StartIn, request: Request, conn: Connection = Depends(get_conn)):
    ip = client_ip(request)
    if _too_many_misses(ip):
        raise HTTPException(429, "Too many tries from here. Wait an hour, or call the office and they can help.")
    acct = _public_account(conn, accountnumber)
    if not signatures.valid_ssn(body.ssn):
        _note_miss(ip)
        raise HTTPException(400, "That Social Security number doesn't look right")
    if body.dob >= date.today() or body.dob.year < 1920:
        raise HTTPException(400, "Check the date of birth")

    ssnhash = signatures.ssn_hash(acct["recordid"], body.ssn)
    match = row(conn, """
        SELECT recordid, status, firstname, lastname FROM drivers
        WHERE accountid = :a AND ssnhash = :h AND dob = :dob AND deleted IS NULL
    """, a=acct["recordid"], h=ssnhash, dob=body.dob)

    # 'appcor' is an application that was read and sent back, so it resumes exactly like one still
    # being filled in.
    if match and match["status"] not in ("application", "appcor"):
        # Known driver: say enough to be useful, never anything about them a stranger shouldn't have.
        messages = {
            "new": "Your application is in. The office is reviewing it and will be in touch.",
            "pending": "Your application is in. The office is reviewing it and will be in touch.",
            "hired": "You're already set up here. Contact the office if you need to update anything.",
            "inactive": "Our records show you're not currently driving here. Contact the office.",
        }
        return {"state": match["status"], "message": messages.get(match["status"], "Contact the office.")}

    if match:
        app_ = row(conn, "SELECT recordid, step FROM driverapplications WHERE driverid = :d", d=match["recordid"])
        if app_ and row(conn, "SELECT 1 AS x FROM driverapplications WHERE recordid = :id AND status = 'submitted'",
                        id=app_["recordid"]):
            return {"state": "pending", "message": "Your application is in. The office is reviewing it."}
        if app_:
            log(conn, None, "driverapply-resume", "driver", match["recordid"], None, ip=ip, accountid=acct["recordid"])
            return {"state": "resume", "token": _token(app_["recordid"]), "step": app_["step"],
                    "firstname": match["firstname"], "lastname": match["lastname"]}

    if not (body.firstname or "").strip() or not (body.lastname or "").strip():
        # Nothing matched. That is how a new applicant starts, and also what guessing looks like,
        # so this is the attempt the brake counts.
        _note_miss(ip)
        return {"state": "new", "needname": True}

    driverid = newid()
    run(conn, """
        INSERT INTO drivers (recordid, accountid, drivernumber, firstname, lastname, status, dob, ssnhash, stub)
        VALUES (:id, :a, :num, :f, :l, 'application', :dob, :h, 0)
    """, id=driverid, a=acct["recordid"], num=drivers.next_number(conn, acct["recordid"]),
        f=body.firstname.strip()[:64], l=body.lastname.strip()[:64], dob=body.dob, h=ssnhash)
    phi.put(conn, acct["recordid"], "driver", driverid, {"ssn": signatures.digits(body.ssn)})
    appid = newid()
    run(conn, """
        INSERT INTO driverapplications (recordid, accountid, driverid, step, data, ip)
        VALUES (:id, :a, :d, 1, '{}', :ip)
    """, id=appid, a=acct["recordid"], d=driverid, ip=ip)
    log(conn, None, "driverapply-start", "driver", driverid, None, ip=ip, accountid=acct["recordid"])
    return {"state": "started", "token": _token(appid), "step": 1,
            "firstname": body.firstname.strip(), "lastname": body.lastname.strip()}


# ------------------------------------------------------------------------------------------------
# The form
# ------------------------------------------------------------------------------------------------

@router.get("/session/state")
def state(app_: dict = Depends(session), conn: Connection = Depends(get_conn)):
    s = _state(app_)
    s["signature"] = signatures.current(conn, app_["accountid"], "driver", app_["driverid"])
    # Each signing carries its own record: which signature event it was, when in UTC, and from where.
    s["signed"] = {k: {"recordid": v["recordid"], "signedon": str(v["signedon"]), "ip": v["ip"]}
                   for k, v in signatures.signed(conn, app_["accountid"], app_["driverid"]).items()}
    s["uploads"] = json.loads(app_["data"] or "{}").get("uploads", {})
    # The last four digits, and nothing more: enough for the applicant to see we hold the right
    # number, never enough to reconstruct it.
    ssn = (phi.get(conn, app_["accountid"], "driver", app_["driverid"]) or {}).get("ssn") or ""
    s["ssnlast4"] = signatures.digits(ssn)[-4:]
    return s


def _keep_licences(conn: Connection, app_: dict, declared: list) -> None:
    """Put the licences the applicant listed onto the driver's own file.

    Until this, step 2 wrote the number and the class onto the `drivers` row and nowhere else, so a
    driver who completed the application had no `driverlicenses` record at all - and both licence
    requirements read that table. The copy requirement said "Nothing on file yet" about a licence
    the driver had just photographed and sent in, which is the complaint that found this.

    Matched on state and number so a resumed application updates its own rows rather than growing a
    new one each time step 2 is saved. The most recently issued is the one marked active, the same
    test the step already uses to decide what goes on the driver record.
    """
    acct, driverid = app_["accountid"], app_["driverid"]
    held = [x for x in (declared or []) if (x.get("number") or "").strip()]
    if not held:
        return
    newest = max(held, key=lambda x: x.get("issued") or "")
    # The photograph of the card, where the applicant has already sent one. It may arrive before
    # this step or after it, so the upload path makes the same link from its own side.
    front = ((json.loads(app_["data"] or "{}").get("uploads") or {})
             .get("license_front") or {}).get("documentid")
    for one in held:
        number = (one.get("number") or "").strip()[:32]
        state = (one.get("state") or "").strip().upper()[:2] or None
        active = 1 if one is newest else 0
        ends = "".join(one.get("endorsements") or []) or None
        got = row(conn, """
            SELECT recordid, copydocumentid FROM driverlicenses
            WHERE accountid = :a AND driverid = :d AND number = :n
              AND (state = :s OR (state IS NULL AND :s IS NULL))
        """, a=acct, d=driverid, n=number, s=state)
        if got:
            run(conn, """
                UPDATE driverlicenses SET classification = :c, endorsements = :e, issued = :i,
                       expires = :x, active = :act, copydocumentid = COALESCE(copydocumentid, :doc),
                       updated = :now
                WHERE recordid = :id
            """, c=(one.get("classification") or None), e=ends, i=(one.get("issued") or None),
                x=(one.get("expires") or None), act=active, doc=front, now=utcnow(),
                id=got["recordid"])
        else:
            run(conn, """
                INSERT INTO driverlicenses (recordid, accountid, driverid, number, state,
                                            classification, endorsements, issued, expires, active,
                                            copydocumentid, note)
                VALUES (:id, :a, :d, :n, :s, :c, :e, :i, :x, :act, :doc, 'From the application')
            """, id=newid(), a=acct, d=driverid, n=number, s=state,
                c=(one.get("classification") or None), e=ends, i=(one.get("issued") or None),
                x=(one.get("expires") or None), act=active, doc=front)
    # Only one licence is the one they drive on.
    run(conn, """
        UPDATE driverlicenses SET active = 0
        WHERE accountid = :a AND driverid = :d AND number <> :n
    """, a=acct, d=driverid, n=(newest.get("number") or "").strip()[:32])


class StepIn(BaseModel):
    step: int
    answers: dict
    advance: bool = True        # false when the applicant is saving to finish later


@router.put("/session/step")
def save_step(body: StepIn, request: Request, app_: dict = Depends(session), conn: Connection = Depends(get_conn)):
    if app_["status"] != "started":
        raise HTTPException(409, "This application has already been submitted")
    if not 1 <= body.step <= STEPS:
        raise HTTPException(400, "Unknown step")
    data = json.loads(app_["data"] or "{}")
    data.setdefault("steps", {})[str(body.step)] = body.answers
    step = max(app_["step"], min(body.step + (1 if body.advance else 0), STEPS))
    run(conn, """
        UPDATE driverapplications SET data = :d, step = :s, updated = :now WHERE recordid = :id
    """, d=json.dumps(data), s=step, now=utcnow(), id=app_["recordid"])
    # Step 1 and 2 hold the details the driver record itself keeps.
    a = body.answers
    if body.step == 1 and (a.get("firstname") or a.get("lastname")):
        run(conn, "UPDATE drivers SET firstname = :f, lastname = :l, phone = :p, email = :e, updated = :now WHERE recordid = :id",
            f=(a.get("firstname") or app_["firstname"])[:64], l=(a.get("lastname") or app_["lastname"])[:64],
            p=(a.get("phone") or None), e=(a.get("email") or None), now=utcnow(), id=app_["driverid"])
    if body.step == 2:
        # The licence they hold now - the most recently issued of the ones listed - is what a trip is
        # judged against, so it is kept on the driver rather than only inside the application.
        held = sorted((a.get("licenses") or []), key=lambda l: l.get("issued") or "", reverse=True)
        current = held[0] if held else {}
        run(conn, """UPDATE drivers SET licensenumber = :n, licensestate = :s, licensesince = :since,
                            licenseclass = :cls, endorsements = :end, updated = :now
                     WHERE recordid = :id""",
            n=(current.get("number") or a.get("licensenumber") or None),
            s=(current.get("state") or a.get("licensestate") or None),
            since=(a.get("licensesince") or None),
            cls=(current.get("classification") or None),
            end="".join(current.get("endorsements") or []) or None,
            now=utcnow(), id=app_["driverid"])
        # And onto the driver's licence file, which is what both licence requirements read.
        _keep_licences(conn, app_, a.get("licenses"))
    saved(conn)
    return {"ok": True, "step": step}


class ProgressIn(BaseModel):
    step: int


@router.put("/session/progress")
def progress(body: ProgressIn, app_: dict = Depends(session), conn: Connection = Depends(get_conn)):
    """How far the applicant has got. Document steps save no answers, so without this a driver who
    signed their way to the last page would come back to the first one that did."""
    step = max(app_["step"], min(max(body.step, 1), STEPS))
    run(conn, "UPDATE driverapplications SET step = :s, updated = :now WHERE recordid = :id",
        s=step, now=utcnow(), id=app_["recordid"])
    saved(conn)
    return {"ok": True, "step": step}


@router.post("/session/upload")
async def upload(kind: str = Form(...), file: UploadFile = File(...), request: Request = None,
                 app_: dict = Depends(session), conn: Connection = Depends(get_conn)):
    if kind not in UPLOAD_KINDS:
        raise HTTPException(400, "Unknown upload")
    data_bytes = await file.read()
    if not data_bytes:
        raise HTTPException(400, "That file is empty")
    if len(data_bytes) > MAX_UPLOAD:
        raise HTTPException(413, "That file is larger than 15 MB")
    declared = (file.content_type or "").split(";")[0].strip().lower()
    if declared not in ALLOWED_TYPES or not _looks_like_a_document(data_bytes, declared):
        raise HTTPException(415, "Upload a photo or a PDF")
    # The same bytes may already be on file - two drivers sending the same blank form, or one
    # applicant sending a file twice. Documents are unique per account by hash, so reuse that row
    # rather than storing a second copy.
    # What a driver sends from a phone is a photograph; what their file needs is a document, so it
    # becomes one here - before it is hashed, because the hash is of what is kept.
    data_bytes, stored_type, stored_name = images.to_pdf(data_bytes, declared, file.filename or kind)
    digest = storage.sha256(data_bytes)
    existing = row(conn, "SELECT recordid, storagekey FROM documents WHERE accountid = :a AND sha256 = :h",
                   a=app_["accountid"], h=digest)
    if existing:
        documentid = existing["recordid"]
        # Reuse the row, but only trust it if the blob is really there: a row whose file has gone
        # would otherwise leave the applicant with an upload they can never open. The bytes go to
        # the key the row already carries - writing them anywhere else leaves the row still wrong.
        if not storage.exists(existing["storagekey"]):
            storage.put_at(existing["storagekey"], data_bytes)
    else:
        documentid = newid()
        key = storage.put(app_["accountid"], "driverapply", documentid, data_bytes)
        run(conn, """
            INSERT INTO documents (recordid, accountid, filename, mimetype, bytes, sha256, storagekey)
            VALUES (:id, :a, :f, :m, :b, :h, :k)
        """, id=documentid, a=app_["accountid"], f=stored_name[:255],
            m=stored_type or "application/octet-stream", b=len(data_bytes), h=digest, k=key)
    data = json.loads(app_["data"] or "{}")
    data.setdefault("uploads", {})[kind] = {"documentid": documentid, "filename": stored_name[:255]}
    # The front of the card IS the copy the licence requirement asks for. Linked here as well as in
    # step 2 because either can happen first: photograph the card then type the number, or the
    # other way round.
    if kind == "license_front":
        run(conn, """
            UPDATE driverlicenses SET copydocumentid = :doc, updated = :now
            WHERE accountid = :a AND driverid = :d AND active = 1
        """, doc=documentid, now=utcnow(), a=app_["accountid"], d=app_["driverid"])
    run(conn, "UPDATE driverapplications SET data = :d, updated = :now WHERE recordid = :id",
        d=json.dumps(data), now=utcnow(), id=app_["recordid"])
    saved(conn)
    return {"ok": True, "kind": kind, "filename": stored_name[:255]}


class ScanOut(BaseModel):
    read: bool


@router.post("/session/scan")
async def scan_license(request: Request, file: UploadFile = File(...), app_: dict = Depends(session)):
    """Read the barcode on the back of a licence and hand back what it says.

    The photograph is not kept: this is a reading, not an upload, and the applicant confirms what it
    found before any of it joins their application."""
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "That image is larger than 15 MB")
    if not _looks_like_a_document(data, file.content_type or ""):
        raise HTTPException(400, "That does not look like a photograph")
    found = licensebarcode.read(data)
    if not found:
        return {"read": False}
    return {"read": True, "license": found}


@router.get("/session/upload/{kind}")
def uploaded_file(kind: str, full: int = 0, app_: dict = Depends(session),
                  conn: Connection = Depends(get_conn)):
    """Give back a file the applicant uploaded, so they can check what they sent.

    A photograph off a phone is several megabytes, and looking at it on screen needs nothing like
    that - so what comes back is scaled to fit a screen unless the full file is asked for. The
    stored file is never touched."""
    if kind not in UPLOAD_KINDS:
        raise HTTPException(400, "Unknown upload")
    documentid = (json.loads(app_["data"] or "{}").get("uploads", {}).get(kind) or {}).get("documentid")
    doc = row(conn, "SELECT filename, mimetype, sha256, storagekey FROM documents WHERE recordid = :id AND accountid = :a",
              id=documentid, a=app_["accountid"]) if documentid else None
    if not doc:
        raise HTTPException(404, "Nothing uploaded yet")
    try:
        data = storage.get(doc["storagekey"])
    except storage.Missing:
        raise HTTPException(410, "That file is no longer stored. Upload it again.")
    mime = doc["mimetype"]
    if not full:
        data, mime = applicationview._fit(data, mime, doc["sha256"])
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f'inline; filename="{doc["filename"]}"',
                             # The same bytes every time for the same file: worth the browser keeping.
                             "Cache-Control": "private, max-age=3600",
                             "ETag": f'"{doc["sha256"][:32]}-{0 if full else 1}"'})


# ------------------------------------------------------------------------------------------------
# Signature and signing
# ------------------------------------------------------------------------------------------------

class SignatureIn(BaseModel):
    dob: date
    ssn: str
    typedname: str | None = None       # defaults to the name on the application
    fontkey: str = "modern"


@router.post("/session/signature")
def adopt_signature(body: SignatureIn, request: Request, app_: dict = Depends(session),
                    conn: Connection = Depends(get_conn)):
    """Date of birth and SSN are checked again at the moment of signing. If this driver already has
    a signature it is the one that gets used - a person signs with one signature, not a new one per
    document - and only a driver without one has it created here."""
    if _too_many_misses(client_ip(request)):
        raise HTTPException(429, "Too many tries from here. Wait an hour, or call the office and they can help.")
    expected = signatures.ssn_hash(app_["accountid"], body.ssn)
    actual = row(conn, "SELECT ssnhash, dob FROM drivers WHERE recordid = :id", id=app_["driverid"])
    if actual["ssnhash"] != expected or actual["dob"] != body.dob:
        _note_miss(client_ip(request))
        raise HTTPException(403, "Incorrect Date Of Birth / Social Security Combination")
    name = f"{app_['firstname']} {app_['lastname']}".strip()
    sig = signatures.current(conn, app_["accountid"], "driver", app_["driverid"])
    # The signature on file is the driver's signature. It is adopted once and cannot be redesigned
    # from the application: every document they sign carries the same hand.
    if sig:
        return sig
    try:
        sig = signatures.adopt(conn, app_["accountid"], "driver", app_["driverid"], name,
                               body.typedname or name, body.fontkey, "dob_ssn",
                               client_ip(request), request.headers.get("user-agent"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    log(conn, None, "driverapply-signature", "driver", app_["driverid"], None,
        ip=client_ip(request), accountid=app_["accountid"])
    saved(conn)
    return sig


class VerifyIn(BaseModel):
    dob: date
    ssn: str


@router.post("/session/verify")
def verify_identity(body: VerifyIn, request: Request, app_: dict = Depends(session),
                    conn: Connection = Depends(get_conn)):
    """Prove that the person at the keyboard is this driver before their signature is shown to them.
    The same date of birth and SSN check that signing itself makes, and the same brake on guessing."""
    ip = client_ip(request)
    if _too_many_misses(ip):
        raise HTTPException(429, "Too many tries from here. Wait an hour, or call the office and they can help.")
    actual = row(conn, "SELECT ssnhash, dob FROM drivers WHERE recordid = :id", id=app_["driverid"])
    if actual["ssnhash"] != signatures.ssn_hash(app_["accountid"], body.ssn) or actual["dob"] != body.dob:
        _note_miss(ip)
        raise HTTPException(403, "Incorrect Date Of Birth / Social Security Combination")
    sig = signatures.current(conn, app_["accountid"], "driver", app_["driverid"])
    return {"ok": True, "signature": {"typedname": sig["typedname"], "fontkey": sig["fontkey"]} if sig else None}


@router.get("/session/document/{doctype}")
def document(doctype: str, app_: dict = Depends(session), conn: Connection = Depends(get_conn)):
    """What is to be signed. For the two company policies that is the file the account filed, shown
    as itself; for everything else it is text the server holds, so what gets hashed is what we
    published."""
    policy = _company_policy(conn, app_["accountid"], doctype)
    if policy:
        return {"doctype": doctype, "title": documents.TITLES[doctype], "source": "company",
                "filename": policy["filename"], "mimetype": policy["mimetype"],
                "version": f"company:{policy['recordid']}", "accountname": app_["accountname"]}
    try:
        doc = documents.driver_document(doctype)
    except KeyError:
        raise HTTPException(404, "Unknown document")
    return documents.fill(doc, _blanks(app_))


def _i9_answers(app_: dict) -> dict:
    """What the I-9 is filled from: the applicant's own details, with the I-9 step's answers on top."""
    data = json.loads(app_["data"]) if app_["data"] else {}
    steps = data.get("steps") or {}
    one = steps.get("1") or {}
    answers = {k: one.get(k) for k in ("middleinitial", "address1", "apt", "city", "state", "zip",
                                       "phone", "email")}
    answers.update({k: v for k, v in (data.get("i9") or {}).items() if v not in (None, "")})
    return answers


def _stored_i9(conn: Connection, app_: dict) -> bytes | None:
    """The signed form as it was stored at the moment of signing, if it has been signed."""
    data = json.loads(app_["data"] or "{}")
    kept = (data.get("signeddocs") or {}).get("I9")
    if not kept:
        return None
    doc = row(conn, "SELECT storagekey FROM documents WHERE recordid = :id", id=kept["documentid"])
    if not doc:
        return None
    try:
        return storage.get(doc["storagekey"])
    except storage.Missing:
        return None


class I9In(BaseModel):
    answers: dict


@router.put("/session/i9")
def save_i9(body: I9In, app_: dict = Depends(session), conn: Connection = Depends(get_conn)):
    """The handful of answers only Form I-9 asks for, kept apart from the application's steps."""
    data = json.loads(app_["data"] or "{}")
    data["i9"] = body.answers
    run(conn, "UPDATE driverapplications SET data = :d, updated = :now WHERE recordid = :id",
        d=json.dumps(data), now=utcnow(), id=app_["recordid"])
    saved(conn)
    return {"ok": True}


@router.get("/session/i9")
def i9_form(app_: dict = Depends(session), conn: Connection = Depends(get_conn)):
    """Page 1 of Form I-9 with Section 1 written into it. Once signed it is the stored copy that is
    served, byte for byte - the form is never rebuilt after the signature is affixed."""
    kept = _stored_i9(conn, app_)
    if kept is None:
        # No stored copy: either it has not been signed yet, or it was signed before the signed copy
        # was kept. Either way the form is drawn from what we hold, signature and all if it has one.
        signed = signatures.signed(conn, app_["accountid"], app_["driverid"]).get("I9")
        sig = signatures.current(conn, app_["accountid"], "driver", app_["driverid"]) or {}
        ssn = (phi.get(conn, app_["accountid"], "driver", app_["driverid"]) or {}).get("ssn")
        kept = i9.build(app_, _i9_answers(app_), ssn,
                        signature=sig.get("typedname") if signed else None,
                        fontkey=sig.get("fontkey") or "signature",
                        signedon=signed["signedon"].date() if signed else None,
                        stamp=signed if signed else None)
    return Response(content=kept, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="form-i-9.pdf"'})


@router.get("/session/policy/{doctype}")
def policy_file(doctype: str, app_: dict = Depends(session), conn: Connection = Depends(get_conn)):
    """The company's own policy, served as the file it is so the applicant reads the real thing."""
    policy = _company_policy(conn, app_["accountid"], doctype)
    if not policy:
        raise HTTPException(404, "That policy has not been filed")
    try:
        data = storage.get(policy["storagekey"])
    except storage.Missing:
        raise HTTPException(410, "That file is no longer stored")
    return Response(content=data, media_type=policy["mimetype"] or "application/octet-stream",
                    headers={"Content-Disposition": f'inline; filename="{policy["filename"]}"'})


class SignIn(BaseModel):
    doctype: str


@router.post("/session/sign")
def sign_document(body: SignIn, request: Request, app_: dict = Depends(session),
                  conn: Connection = Depends(get_conn)):
    """Sign by document type only: the server hashes its own copy of the text, so the record cannot
    be made to attest to something the applicant was never shown."""
    sig = signatures.current(conn, app_["accountid"], "driver", app_["driverid"])
    if not sig:
        raise HTTPException(409, "Create your signature first")
    # A company policy is signed against the SHA-256 of the exact file that was shown.
    policy = _company_policy(conn, app_["accountid"], body.doctype)
    if policy:
        try:
            signatures.sign(conn, app_["accountid"], sig["recordid"], body.doctype, app_["driverid"], "",
                            contenthash=policy["sha256"], version=f"company:{policy['recordid']}",
                            ip=client_ip(request), useragent=request.headers.get("user-agent"))
        except ValueError as e:
            raise HTTPException(400, str(e))
        saved(conn)
        return {"ok": True, "doctype": body.doctype, "signedon": str(utcnow())}
    if body.doctype == "I9":
        # 8 CFR 274a.2(h)(1): the system must have a way for the signer to acknowledge they have
        # read the attestation, and the signature is affixed at the time of the transaction. The
        # signed form is built once, stored as it stands, and served from the store from then on.
        data = json.loads(app_["data"] or "{}")
        if not (data.get("i9") or {}).get("acknowledged"):
            raise HTTPException(400, "Acknowledge that you have read the attestation first")
        ssn = (phi.get(conn, app_["accountid"], "driver", app_["driverid"]) or {}).get("ssn")
        # The stamp beside the signature names this signing, so its id and time are settled first.
        recordid, when, ip = newid(), utcnow(), client_ip(request)
        pdf = i9.build(app_, _i9_answers(app_), ssn, signature=sig["typedname"],
                       fontkey=sig["fontkey"], signedon=date.today(),
                       stamp={"recordid": recordid, "signedon": when, "ip": ip})
        digest = storage.sha256(pdf)
        documentid = newid()
        key = storage.put(app_["accountid"], "driverapply", documentid, pdf)
        run(conn, """
            INSERT INTO documents (recordid, accountid, filename, mimetype, bytes, sha256, storagekey)
            VALUES (:id, :a, 'form-i-9-signed.pdf', 'application/pdf', :b, :h, :k)
        """, id=documentid, a=app_["accountid"], b=len(pdf), h=digest, k=key)
        data.setdefault("signeddocs", {})["I9"] = {"documentid": documentid, "sha256": digest}
        run(conn, "UPDATE driverapplications SET data = :d, updated = :now WHERE recordid = :id",
            d=json.dumps(data), now=utcnow(), id=app_["recordid"])
        signatures.sign(conn, app_["accountid"], sig["recordid"], "I9", app_["driverid"], "",
                        contenthash=digest, version=i9.I9_EDITION, ip=ip,
                        useragent=request.headers.get("user-agent"), recordid=recordid, signedon=when)
        saved(conn)
        return {"ok": True, "doctype": "I9", "signedon": str(when)}
    try:
        doc = documents.fill(documents.driver_document(body.doctype), _blanks(app_))
    except KeyError:
        raise HTTPException(404, "Unknown document")
    try:
        signatures.sign(conn, app_["accountid"], sig["recordid"], body.doctype, app_["driverid"], doc["text"],
                        version=doc["version"], ip=client_ip(request), useragent=request.headers.get("user-agent"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "doctype": body.doctype, "signedon": str(utcnow())}


def account_inbox(conn: Connection, accountid: str) -> list[str]:
    """Where a company's own mail goes: its general address, then support, then whoever administers
    the account - the first that is set, so something always reaches a person."""
    acct = row(conn, """
        SELECT a.email, a.supportemail, u.email AS adminemail
        FROM accounts a LEFT JOIN users u ON u.recordid = a.primaryuserid
        WHERE a.recordid = :a
    """, a=accountid)
    for field in ("email", "supportemail", "adminemail"):
        if acct and acct[field]:
            return [acct[field]]
    return []


def _driver_email(conn: Connection, app_: dict) -> str | None:
    one = (json.loads(app_["data"] or "{}").get("steps") or {}).get("1") or {}
    return one.get("email") or row(conn, "SELECT email FROM drivers WHERE recordid = :id",
                                   id=app_["driverid"])["email"]


# What the driver keeps: the acknowledgements they signed on the way through, as they signed
# them. A person who has just handed over their history and their signature should not have to ask
# the company for a copy of what they agreed to.
RECEIPT_DOCS = ("PHI_ACK", "WORKPLACE_POLICY", "DRUG_POLICY")


def _joined(policy: bytes | None, affidavit: bytes) -> bytes:
    """The document the driver was given, with the page they signed behind it.

    The portal shows the filed policy inside the page it draws, by embedding it. A printer cannot
    do that - WeasyPrint draws the page, not the file inside it - so the two PDFs are joined here
    instead. Without this the driver receives a signature page attesting to a policy that is not in
    the attachment."""
    if not policy:
        return affidavit
    try:
        writer = PdfWriter()
        for part in (policy, affidavit):
            for page in PdfReader(io.BytesIO(part)).pages:
                writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        log_render.exception("could not join the filed policy to its signature page")
        return affidavit


def _signed_copies(conn: Connection, accountid: str, driverid: str) -> list[tuple[str, bytes, str]]:
    """The three acknowledgements as PDFs - the policy itself with its signature page - drawn now,
    because the background task that sends them runs after this request's connection has closed."""
    out = []
    for doctype in RECEIPT_DOCS:
        try:
            view = applicationview.signed_document(conn, accountid, driverid, doctype)
            if not view:
                continue
            filed = applicationview._company_policy(conn, accountid,
                                                    applicationview.POLICY_CODES.get(doctype))
            policy = None
            if filed and (filed["mimetype"] or "").endswith("pdf"):
                try:
                    policy = storage.get(filed["storagekey"])
                except storage.Missing:
                    policy = None
            name = view["title"].replace("/", "-")[:80]
            affidavit = applicationview.to_pdf(view, applicationview.signature_css())
            out.append((f"{name}.pdf", _joined(policy, affidavit), "application/pdf"))
        except Exception:
            # A copy that will not draw is not a reason to withhold the receipt itself.
            log_render.exception("could not render %s for the application receipt", doctype)
    return out


def tell_them_it_arrived(*, name: str, accountname: str, driver: str | None, inboxes: list[str],
                         link: str, cmv: bool, signed: int,
                         copies: list[tuple[str, bytes, str]] | None = None) -> None:
    """Two emails on submission: a receipt for the driver, and a nudge for the office.

    Everything it needs is read during the request and handed over as plain values. A background
    task runs after the response, when the request's transaction is already closing - querying on
    that connection took the submission down with it."""
    if driver:
        subject, html, text = emails.application_received(name=name, accountname=accountname)
        mailer.send(driver, subject, html, text, attachments=copies)
    for inbox in inboxes:
        subject, html, text = emails.application_submitted(
            drivername=name, accountname=accountname, link=link, cmv=cmv, documents=signed)
        mailer.send(inbox, subject, html, text)


@router.post("/session/submit")
def submit(request: Request, tasks: BackgroundTasks, app_: dict = Depends(session),
           conn: Connection = Depends(get_conn)):
    if app_["status"] != "started":
        raise HTTPException(409, "This application has already been submitted")
    have = set(signatures.signed(conn, app_["accountid"], app_["driverid"]))
    # The two commercial consents are only asked of a driver who said they will operate a commercial
    # vehicle for the company, so they are not missing from anyone else's application.
    data = json.loads(app_["data"] or "{}")
    # A commercial driver is one who holds a commercial licence: the card decides, not a question.
    licences = ((data.get("steps") or {}).get("2") or {}).get("licenses") or []
    cmv = any((l.get("classification") or "").upper() in ("A", "B", "C") for l in licences)
    wanted = [d for d in STEP_DOCS.values() if d not in CMV_DOCS or cmv]
    missing = [d for d in wanted if d not in have]
    if missing:
        raise HTTPException(400, f"Still to sign: {', '.join(missing)}")
    run(conn, """
        UPDATE driverapplications SET status = 'submitted', submittedon = :now, updated = :now WHERE recordid = :id
    """, now=utcnow(), id=app_["recordid"])
    # A finished application makes the driver new to the company: theirs is done, the office's is not.
    run(conn, "UPDATE drivers SET status = 'new', updated = :now WHERE recordid = :id",
        now=utcnow(), id=app_["driverid"])
    log(conn, None, "driverapply-submit", "driver", app_["driverid"], None,
        ip=client_ip(request), accountid=app_["accountid"])
    events.record(conn, app_["accountid"], "driver", app_["driverid"], "application-submitted",
                  label=f'{app_["firstname"].title()} {app_["lastname"].title()} submitted their '
                        'driver application')
    tasks.add_task(
        tell_them_it_arrived,
        name=f"{app_['firstname']} {app_['lastname']}".strip(), accountname=app_["accountname"],
        driver=_driver_email(conn, app_), inboxes=account_inbox(conn, app_["accountid"]),
        link=f"{settings.public_url.rstrip('/')}/drivers/{app_['driverid']}", cmv=cmv, signed=len(have),
        copies=_signed_copies(conn, app_["accountid"], app_["driverid"]))
    saved(conn)
    return {"ok": True, "state": "submitted"}
