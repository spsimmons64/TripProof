###################################################################################################
# Asking a driver for a document they hold, and taking it when it comes.
#
# Some requirements can only be answered by paper the driver has and the company does not - the
# notice a state sent when a license was acted against, a certificate from a course taken before
# they arrived. The office's alternatives were to stand over the driver or to wait, and in the
# meantime nothing recorded that anybody had asked.
#
# This is the signing request's twin, and follows it deliberately:
#
#   the office asks     -> a row, a random token, an email with the link
#   the driver opens it -> what is wanted and who wants it, and nothing else given away
#   the driver proves   -> date of birth and Social Security number, as in the application
#   the driver uploads  -> the file lands as a credential on their file
#
# The token alone uploads nothing. It says which document is wanted, not who is sitting at it, so
# a forwarded email cannot put a file on somebody's record.
#
# WHAT THE PAGE DOES NOT SAY
#
# The reason a document is wanted is often the driver's own license history, and a page opened on a
# phone is read by whoever is standing behind them. So the page names the company and the document
# and stops there - no requirement, no citation, no explanation of why it is being asked.
###################################################################################################
import json
import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import events, images, questionnaireview, signatures, storage
from app.activity import log
from app.config import settings
from app.db import get_conn, newid, row, run, saved, utcnow
from app.security import client_ip

router = APIRouter(prefix="/api/upload-request", tags=["uploading"])

# Long enough to reach somebody who checks their email weekly, short enough that a forwarded message
# is not a standing invitation. The same fortnight a signing request gets.
VALID_DAYS = 14

# A photograph of a certificate is a photograph, not a scan, and phones make large ones.
MAX_BYTES = 20 * 1024 * 1024
ACCEPTS = ("application/pdf", "image/jpeg", "image/png", "image/heic", "image/heif", "image/webp")

# What there is no exemption from. A driver either holds a license or does not drive, so offering
# "I am exempt" against one is offering an answer that cannot be true.
NO_EXEMPTION = ("DRIVER_LICENSE", "PREEMP_DA_QUESTIONNAIRE")

# What is asked for is not always a document. 49 CFR 40.25(j) is a question only the applicant can
# answer, so the link shows the question instead of a file picker and what comes back is an answer.
QUESTIONNAIRE = "PREEMP_DA_QUESTIONNAIRE"


def link_for(token: str) -> str:
    return f"{settings.public_url.rstrip('/')}/upload/{token}"


def create(conn: Connection, accountid: str, driverid: str, code: str,
           requestedby: str | None = None) -> dict:
    """A fresh request for one document, replacing any earlier one still outstanding for it.

    Two live links for the same document is two ways to lose track of which was used, and a driver
    with two emails cannot tell which one the company meant."""
    # The license is kept in driverlicenses and the questionnaire's answers in their own table, not
    # the catalog, so their catalog rows being switched off (220) says nothing about whether a
    # driver can be asked for one.
    kind = row(conn, "SELECT recordid, code, name FROM credentialtypes "
                     "WHERE code = :c AND subject = 'driver' "
                     "AND (active = 1 OR code IN ('DRIVER_LICENSE', :q))", c=code, q=QUESTIONNAIRE)
    if not kind:
        raise HTTPException(400, "That is not a document a driver can be asked for")
    run(conn, """
        UPDATE uploadrequests SET cancelledon = :now
        WHERE accountid = :a AND driverid = :d AND credentialcode = :c
          AND uploadedon IS NULL AND cancelledon IS NULL
    """, now=utcnow(), a=accountid, d=driverid, c=code)
    token = secrets.token_urlsafe(32)
    rid = newid()
    run(conn, """
        INSERT INTO uploadrequests (recordid, accountid, driverid, credentialcode, token,
                                    expireson, requestedby)
        VALUES (:id, :a, :d, :c, :tok, :exp, :u)
    """, id=rid, a=accountid, d=driverid, c=code, tok=token,
        exp=utcnow() + timedelta(days=VALID_DAYS), u=requestedby)
    return {"recordid": rid, "token": token, "link": link_for(token), "days": VALID_DAYS,
            "document": kind["name"], "credentialtypeid": kind["recordid"]}


def _open_request(conn: Connection, token: str) -> dict:
    held = row(conn, """
        SELECT r.recordid, r.accountid, r.driverid, r.credentialcode, r.expireson, r.uploadedon,
               r.cancelledon, d.firstname, d.lastname, d.dob, d.ssnhash, a.name AS accountname,
               t.recordid AS credentialtypeid, t.name AS document
        FROM uploadrequests r
        JOIN drivers d ON d.recordid = r.driverid
        JOIN accounts a ON a.recordid = r.accountid
        JOIN credentialtypes t ON t.code = r.credentialcode
        WHERE r.token = :tok
    """, tok=token)
    if not held:
        raise HTTPException(404, "That link is not valid")
    if held["cancelledon"]:
        raise HTTPException(410, "That link has been replaced by a newer one")
    if held["uploadedon"]:
        raise HTTPException(409, "That document has already been sent")
    if held["expireson"] < utcnow():
        raise HTTPException(410, "That link has expired - ask the company for a new one")
    return held


def _prove(held: dict, dob: date, ssn: str) -> None:
    """The same check the application makes, against the same record."""
    if not signatures.valid_ssn(ssn):
        raise HTTPException(400, "That Social Security number doesn't look right")
    if (held["ssnhash"] != signatures.ssn_hash(held["accountid"], ssn) or held["dob"] != dob):
        raise HTTPException(403, "Incorrect Date Of Birth / Social Security Combination")


@router.get("/{token}")
def what_is_being_asked(token: str, conn: Connection = Depends(get_conn)):
    """What the link is for, before anybody proves anything: the company, the document, and the
    first name of the person it is meant for. Nothing that would tell a stranger who the driver
    is, and nothing about why it is wanted."""
    held = _open_request(conn, token)
    return {"accountname": held["accountname"], "document": held["document"],
            "firstname": (held["firstname"] or "").title(),
            "license": held["credentialcode"] == "DRIVER_LICENSE",
            "questionnaire": held["credentialcode"] == QUESTIONNAIRE,
            "exemptable": held["credentialcode"] not in NO_EXEMPTION}


class Prove(BaseModel):
    dob: date
    ssn: str


@router.post("/{token}/open")
def open_it(token: str, body: Prove, conn: Connection = Depends(get_conn)):
    """Prove who is at the keyboard, and be shown what to send."""
    held = _open_request(conn, token)
    _prove(held, body.dob, body.ssn)
    # The signature they already adopted on their application, sent back so the page can SHOW it
    # rather than ask for it again. A person has one signature; they adopted it once, on their own
    # application, and everything they sign afterwards is signed with that one. Only once they have
    # proved who they are - an unproven caller is told nothing about the driver.
    sig = signatures.current(conn, held["accountid"], "driver", held["driverid"])
    return {"accountname": held["accountname"], "document": held["document"],
            "firstname": (held["firstname"] or "").title(),
            "license": held["credentialcode"] == "DRIVER_LICENSE",
            "questionnaire": held["credentialcode"] == QUESTIONNAIRE,
            "signature": ({"typedname": sig["typedname"], "fontkey": sig["fontkey"]}
                          if sig else None),
            "exemptable": held["credentialcode"] not in NO_EXEMPTION}


async def _take_questionnaire(conn: Connection, request: Request, held: dict, priorviolation,
                              prioremployer, priortestdate, priortesttype, priorrtd,
                              signature=None, fontkey=None, paperwork=None):
    """The 40.25(j) answer, written onto the driver's own application.

    There is no document and no credential: the application IS the record, and the rule already
    reads the answer from it. Writing it anywhere else would make a second copy of a fact."""
    said = (priorviolation or "").strip().lower()
    if said not in ("yes", "no"):
        raise HTTPException(400, "Answer the question")
    # 40.25(j) is an attestation, not a form: what makes it one is the driver putting their name to
    # it. They sign it with THEIR OWN signature - the one they adopted on their application - so
    # there is nothing to type and no hand to choose. Only a driver who has never signed anything
    # here adopts one now, and proving the pair is what adopting takes.
    sig = signatures.current(conn, held["accountid"], "driver", held["driverid"])
    typed = (signature or "").strip()
    if not sig and not typed:
        raise HTTPException(400, "Sign the questionnaire before sending it")
    if said == "yes" and not (prioremployer or "").strip():
        raise HTTPException(400, "Say which employer you applied to")
    app_ = row(conn, """
        SELECT recordid, data FROM driverapplications
        WHERE driverid = :d AND accountid = :a ORDER BY startedon DESC LIMIT 1
    """, d=held["driverid"], a=held["accountid"])
    if not app_:
        raise HTTPException(409, "This driver has no application to record the answer on")
    try:
        data = json.loads(app_["data"] or "{}") or {}
    except ValueError:
        data = {}
    # Whatever they hold showing the return-to-duty process was done - the SAP's determination, a
    # follow-up testing plan, a negative return-to-duty result. Only where there is a violation to
    # document, and never required: a driver may have disclosed one and have nothing in their hand.
    # It is not filed on its own: it is bound onto the form below, because the driver filled in one
    # form once and the file should hold one document for it.
    attachment = await _one_side(paperwork) if said == "yes" else None
    data.setdefault("steps", {})["10"] = {
        "priorviolation": said,
        "prioremployer": (prioremployer or "").strip().upper() or None,
        "priortestdate": (priortestdate or "").strip() or None,
        "priortesttype": (priortesttype or "").strip().lower() or None,
        "priorrtd": (priorrtd or "").strip().lower() or None,
        "attached": bool(attachment),
    }
    run(conn, "UPDATE driverapplications SET data = :x, updated = NOW() WHERE recordid = :i",
        x=json.dumps(data), i=app_["recordid"])
    run(conn, "UPDATE uploadrequests SET uploadedon = :now WHERE recordid = :id",
        now=utcnow(), id=held["recordid"])
    name = f'{held["firstname"]} {held["lastname"]}'.strip()

    # What is hashed is the answer they gave, so the record says what was attested to and not
    # merely that something was.
    if not sig:
        try:
            sig = signatures.adopt(conn, held["accountid"], "driver", held["driverid"], name,
                                   typed, (fontkey or "modern"), "dob_ssn", client_ip(request),
                                   request.headers.get("user-agent"))
        except ValueError as e:
            raise HTTPException(400, str(e))
    attested = (f'49 CFR 40.25(j) - answered {said}'
                + (f'; {prioremployer}, {priortestdate}, {priortesttype}, '
                   f'return to duty {priorrtd}' if said == "yes" else ""))
    signatures.sign(conn, held["accountid"], sig["recordid"], QUESTIONNAIRE, held["driverid"],
                    attested, ip=client_ip(request),
                    useragent=request.headers.get("user-agent"))
    # The form itself, drawn now that it is signed: the question in the words it was asked, the
    # answer given, and the signature under it. Filed against the request, which is what puts it in
    # front of somebody - a document that came down a link is unread until the office says it read
    # it, and this is the thing they read.
    questionnaireview.keep(conn, held["accountid"], held["driverid"],
                           data["steps"]["10"], held["recordid"], attachment)
    log(conn, None, "answered-on-request", "driver", held["driverid"],
        {"credentialcode": held["credentialcode"], "answer": said}, ip=client_ip(request),
        accountid=held["accountid"])
    events.record(conn, held["accountid"], "driver", held["driverid"], "uploaded",
                  held["credentialcode"],
                  label=f'{name.title()} answered the pre-employment questionnaire')
    saved(conn)
    return {"ok": True, "accountname": held["accountname"], "document": held["document"]}


async def _one_side(side: UploadFile | None) -> bytes | None:
    if side is None or not side.filename:
        return None
    data = await side.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "That file is larger than 20 MB")
    page, mimetype, _name = images.to_pdf(data, side.content_type, side.filename)
    if mimetype != "application/pdf":
        raise HTTPException(415, "Send a photograph or a PDF")
    return page


async def _take_license(conn: Connection, request: Request, held: dict, number, state,
                        classification, endorsements, issued, expires, front, back):
    """The license the driver typed in, and the copy of it, filed the way the office files one.

    The front and the back become one PDF - see app/images.py - so what ends up on the license is
    the card, not two snapshots that have to be read together."""
    number = (number or "").strip().upper()
    state = (state or "").strip().upper()[:2]
    if not number or len(state) != 2:
        raise HTTPException(400, "The license number and state are required")
    if not issued or not expires:
        raise HTTPException(400, "The issue and expiration dates are required")
    if expires < issued:
        raise HTTPException(400, "The expiry date is before the issue date")
    pages = [p for p in [await _one_side(front), await _one_side(back)] if p]
    if not pages:
        raise HTTPException(400, "Send at least one side of the license")

    documentid = storage.keep(conn, held["accountid"], "documents", images.bind(pages),
                              "License.pdf", "application/pdf", None, origin=storage.DRIVER)
    # The same license typed in twice is the same license, so it is corrected rather than doubled.
    already = row(conn, """
        SELECT recordid FROM driverlicenses
        WHERE accountid = :a AND driverid = :d AND state = :s AND number = :n
    """, a=held["accountid"], d=held["driverid"], s=state, n=number)
    lid = already["recordid"] if already else newid()
    if already:
        run(conn, """
            UPDATE driverlicenses SET classification = :c, endorsements = :e, issued = :i,
                   expires = :x, copydocumentid = :doc, updated = :now WHERE recordid = :id
        """, c=(classification or None), e=(endorsements or None), i=issued, x=expires,
            doc=documentid, now=utcnow(), id=lid)
    else:
        run(conn, """
            INSERT INTO driverlicenses (recordid, accountid, driverid, number, state, classification,
                                        endorsements, issued, expires, copydocumentid)
            VALUES (:id, :a, :d, :n, :s, :c, :e, :i, :x, :doc)
        """, id=lid, a=held["accountid"], d=held["driverid"], n=number, s=state,
            c=(classification or None), e=(endorsements or None), i=issued, x=expires,
            doc=documentid)
    # The first license on file is the one they drive on until somebody says otherwise. A driver
    # sending one in does not get to decide that, so an existing active license is left alone.
    if not row(conn, "SELECT 1 AS x FROM driverlicenses WHERE accountid = :a AND driverid = :d"
                     " AND active = 1", a=held["accountid"], d=held["driverid"]):
        run(conn, "UPDATE driverlicenses SET active = 1 WHERE recordid = :id", id=lid)

    name = f'{held["firstname"]} {held["lastname"]}'.strip()
    run(conn, """
        UPDATE uploadrequests SET uploadedon = :now, documentid = :doc WHERE recordid = :id
    """, now=utcnow(), doc=documentid, id=held["recordid"])
    log(conn, None, "uploaded-on-request", "driver", held["driverid"],
        {"credentialcode": held["credentialcode"], "state": state}, ip=client_ip(request),
        accountid=held["accountid"])
    events.record(conn, held["accountid"], "driver", held["driverid"], "uploaded",
                  held["credentialcode"], label=f'{name.title()} sent their {state} license')
    saved(conn)
    return {"ok": True, "accountname": held["accountname"], "document": held["document"]}


@router.post("/{token}")
async def send_it(token: str, request: Request, dob: date = Form(...), ssn: str = Form(...),
                  issuedon: date | None = Form(None), expireson: date | None = Form(None),
                  exempt: bool = Form(False), file: UploadFile | None = File(None),
                  number: str | None = Form(None), state: str | None = Form(None),
                  classification: str | None = Form(None), endorsements: str | None = Form(None),
                  front: UploadFile | None = File(None), back: UploadFile | None = File(None),
                  priorviolation: str | None = Form(None), prioremployer: str | None = Form(None),
                  priortestdate: str | None = Form(None), priortesttype: str | None = Form(None),
                  priorrtd: str | None = Form(None),
                  signature: str | None = Form(None), fontkey: str | None = Form(None),
                  conn: Connection = Depends(get_conn)):
    """Take the file. It becomes a credential on the driver's file, which is what the requirement
    reads - so the document answers the requirement the moment it lands, with nobody re-filing it.

    A driver who is exempt has no document to send, and saying so is the answer rather than a gap.
    That is the one case where nothing is attached, and it is recorded as an exemption rather than
    as a certificate that happens to be missing."""
    held = _open_request(conn, token)
    _prove(held, dob, ssn)
    if exempt and held["credentialcode"] in NO_EXEMPTION:
        raise HTTPException(400, "There is no exemption from this one")
    # A license is not a document that happens to be a license. It is a card with a number, a state,
    # a class and two sides, and the file is the copy OF it - so the whole card is taken here, the
    # same as the office takes it, rather than a photograph with nothing recorded about what it is.
    if held["credentialcode"] == QUESTIONNAIRE:
        return await _take_questionnaire(conn, request, held, priorviolation, prioremployer,
                                         priortestdate, priortesttype, priorrtd, signature,
                                         fontkey, file)
    if held["credentialcode"] == "DRIVER_LICENSE":
        return await _take_license(conn, request, held, number, state, classification,
                                   endorsements, issuedon, expireson, front, back)
    data = None
    if not exempt:
        if file is None or not file.filename:
            raise HTTPException(400, "Attach the document")
        data = await file.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "That file is larger than 20 MB")
        if file.content_type and file.content_type not in ACCEPTS:
            raise HTTPException(415, "Send a PDF or a photograph")
    if exempt:
        # No document means no dates off it. The record is dated the day they said so.
        issuedon, expireson = None, None
    if expireson and issuedon and expireson < issuedon:
        raise HTTPException(400, "The expiry date is before the issue date")

    documentid = None
    if data is not None:
        documentid = storage.keep(conn, held["accountid"], "documents", data, file.filename,
                                  file.content_type, None, origin=storage.DRIVER)
    name = f'{held["firstname"]} {held["lastname"]}'.strip()
    credentialid = newid()
    run(conn, """
        INSERT INTO credentials (recordid, accountid, credentialtypeid, subject, subjectid,
                                 documentid, issuedon, expireson, exempt, issuer, notes)
        VALUES (:id, :a, :t, 'driver', :d, :doc, :on, :ends, :ex, :by, :n)
    """, id=credentialid, a=held["accountid"], t=held["credentialtypeid"], d=held["driverid"],
        doc=documentid, on=issuedon, ends=expireson, ex=1 if exempt else 0,
        by=name[:128] or None,
        n="The driver says they are exempt" if exempt else "Sent by the driver")
    # A license copy is not a credential filed beside the license - it is the copy OF the license,
    # and the requirement reads it off the license row. Sent any other way it would land on the file
    # and the requirement would go on saying nothing is on file.
    if documentid and held["credentialcode"] == "DRIVER_LICENSE":
        run(conn, """
            UPDATE driverlicenses SET copydocumentid = :doc
            WHERE recordid = (SELECT recordid FROM (
                SELECT recordid FROM driverlicenses
                WHERE accountid = :a AND driverid = :d
                ORDER BY active DESC, issued DESC LIMIT 1) AS pick)
        """, doc=documentid, a=held["accountid"], d=held["driverid"])
    run(conn, """
        UPDATE uploadrequests SET uploadedon = :now, documentid = :doc, credentialid = :c
        WHERE recordid = :id
    """, now=utcnow(), doc=documentid, c=credentialid, id=held["recordid"])
    log(conn, None, "uploaded-on-request", "driver", held["driverid"],
        {"credentialcode": held["credentialcode"]}, ip=client_ip(request),
        accountid=held["accountid"])
    events.record(conn, held["accountid"], "driver", held["driverid"], "uploaded",
                  held["credentialcode"],
                  label=f'{name.title()} sent the {held["document"].lower()}')
    saved(conn)
    return {"ok": True, "accountname": held["accountname"], "document": held["document"]}
