###################################################################################################
# Signing one document, after the application is in.
#
# A driver's file is never finished the way an application is. A policy is revised, a consent was
# never given, a form was signed on paper and lost. The application closes when it is submitted, so
# without this the office's only options are to stand over the driver or to file a paper copy that
# nothing can verify.
#
# A signing request is one document, for one driver, reachable by one link:
#
#   the office asks     -> a row, a random token, an email with the link
#   the driver opens it -> the document is shown, unsigned, with nothing given away yet
#   the driver proves   -> date of birth and Social Security number, as in the application
#   the driver signs    -> their signature on file, or one adopted here, against our own copy
#
# The token alone signs nothing: it says which document is on the table, not who is sitting at it.
###################################################################################################
import hashlib
import json
import secrets
from datetime import date, datetime, timedelta
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import documents, events, i9, pdfform, phi, signatures, storage, w4
from app.activity import log
from app.config import settings
from app.db import get_conn, newid, row, run, saved, utcnow
from app.security import client_ip

router = APIRouter(prefix="/api/sign", tags=["signing"])

# How long a link stays alive. Long enough to reach somebody who checks their email weekly, short
# enough that a forwarded message is not a standing invitation.
VALID_DAYS = 14

# What a driver can be asked to sign this way: their own acknowledgements and consents. Not the
# application, which is a form they fill in rather than a document they are handed, and not
# anything an employer signs about them.
# The two the office sends the moment somebody is hired. They are not acknowledgements of our
# wording - they are the government's own forms, so they are rendered as the real PDF and signed on
# it, never as a rendition of it in our words.
ON_PAPER = {
    "I9": "Form I-9, Employment Eligibility Verification",
    "W4": "Form W-4, Employee's Withholding Certificate",
}

# Not a document to read - a form the driver fills in and then signs, where what is signed is
# the figures they entered rather than wording of ours. 49 CFR 395.8(j)(2): the hours they had
# already worked before they got here, which the carrier has to know before it dispatches them.
FILLED_IN = {
    "PREV7_ONDUTY": "Previous 7 Days' On-Duty Hours Statement",
}

SIGNABLE = {
    **ON_PAPER,
    **FILLED_IN,
    "FCRA_AUTH": "Background check disclosure and authorization",
    "FCRA_SUMMARY": "A Summary of Your Rights Under the Fair Credit Reporting Act",
    "WORKPLACE_POLICY": "Workplace policy acknowledgement",
    "DRUG_POLICY": "Drug and alcohol policy acknowledgement",
    "PHI_ACK": "PHI confidentiality and privacy acknowledgment",
    "CLEARINGHOUSE_CONSENT": "FMCSA Clearinghouse query consent",
    "SAFETY_PERFORMANCE_CONSENT": "Consent to release safety performance history",
}


def link_for(token: str) -> str:
    return f"{settings.public_url.rstrip('/')}/sign/{token}"


def create(conn: Connection, accountid: str, driverid: str, doctype: str,
           requestedby: str | None = None) -> dict:
    """A fresh request for one document, replacing any earlier one still outstanding for it - two
    live links to the same document is two ways to lose track of which was used."""
    if doctype not in SIGNABLE:
        raise HTTPException(400, "That is not a document a driver signs")
    run(conn, """
        UPDATE signingrequests SET cancelledon = :now
        WHERE accountid = :a AND driverid = :d AND doctype = :t
          AND signedon IS NULL AND cancelledon IS NULL
    """, now=utcnow(), a=accountid, d=driverid, t=doctype)
    token = secrets.token_urlsafe(32)
    rid = newid()
    run(conn, """
        INSERT INTO signingrequests (recordid, accountid, driverid, doctype, token, expireson, requestedby)
        VALUES (:id, :a, :d, :t, :tok, :exp, :u)
    """, id=rid, a=accountid, d=driverid, t=doctype, tok=token,
        exp=utcnow() + timedelta(days=VALID_DAYS), u=requestedby)
    return {"recordid": rid, "token": token, "link": link_for(token), "days": VALID_DAYS}


def _open_request(conn: Connection, token: str) -> dict:
    held = row(conn, """
        SELECT r.recordid, r.accountid, r.driverid, r.doctype, r.expireson, r.signedon, r.cancelledon,
               d.firstname, d.lastname, d.dob, d.ssnhash, a.name AS accountname
        FROM signingrequests r
        JOIN drivers d ON d.recordid = r.driverid
        JOIN accounts a ON a.recordid = r.accountid
        WHERE r.token = :tok
    """, tok=token)
    if not held:
        raise HTTPException(404, "That link is not valid")
    if held["cancelledon"]:
        raise HTTPException(410, "That link has been replaced by a newer one")
    if held["signedon"]:
        raise HTTPException(409, "That document has already been signed")
    if held["expireson"] < utcnow():
        raise HTTPException(410, "That link has expired - ask the company for a new one")
    return held


def _still_owed(conn: Connection, accountid: str, driverid: str, besides: str | None = None):
    """The next thing this driver has been asked to sign and has not."""
    return row(conn, """
        SELECT doctype, token FROM signingrequests
        WHERE accountid = :a AND driverid = :d AND recordid <> COALESCE(:id, '')
          AND signedon IS NULL AND cancelledon IS NULL AND expireson > :now
        ORDER BY createdon LIMIT 1
    """, a=accountid, d=driverid, id=besides, now=utcnow())


@router.get("/{token}")
def what_is_being_asked(token: str, conn: Connection = Depends(get_conn)):
    """What the link is for, before anybody proves anything: the company, the document, and the
    first name of the person it is meant for. Nothing that would tell a stranger who the driver is.

    A link that has already been signed is not an error when the same driver still owes something
    else. The welcome email carries ONE link and asks for two forms, so coming back to it after
    signing the first has to land on the second rather than on a refusal."""
    gone = row(conn, """
        SELECT r.recordid, r.accountid, r.driverid, r.signedon, r.cancelledon, d.firstname,
               a.name AS accountname
        FROM signingrequests r
          JOIN drivers d ON d.recordid = r.driverid
          JOIN accounts a ON a.recordid = r.accountid
        WHERE r.token = :tok
    """, tok=token)
    if gone and gone["signedon"] and not gone["cancelledon"]:
        nxt = _still_owed(conn, gone["accountid"], gone["driverid"], gone["recordid"])
        if nxt:
            return {"accountname": gone["accountname"], "doctype": nxt["doctype"],
                    "title": SIGNABLE.get(nxt["doctype"], nxt["doctype"]),
                    "firstname": (gone["firstname"] or "").title(),
                    # The page follows this rather than showing a refusal.
                    "insteadof": nxt["token"]}
    held = _open_request(conn, token)
    return {"accountname": held["accountname"], "doctype": held["doctype"],
            "title": SIGNABLE.get(held["doctype"], held["doctype"]),
            "firstname": (held["firstname"] or "").title()}


class Prove(BaseModel):
    dob: date
    ssn: str


@router.post("/{token}/read")
def read_it(token: str, body: Prove, conn: Connection = Depends(get_conn)):
    """Prove who is at the keyboard, and be given the document to read. The same check the
    application makes, against the same record."""
    held = _open_request(conn, token)
    if not signatures.valid_ssn(body.ssn):
        raise HTTPException(400, "That Social Security number doesn't look right")
    if (held["ssnhash"] != signatures.ssn_hash(held["accountid"], body.ssn)
            or held["dob"] != body.dob):
        raise HTTPException(403, "Incorrect Date Of Birth / Social Security Combination")
    _recognise(conn, held, body)
    sig = signatures.current(conn, held["accountid"], "driver", held["driverid"])
    if held["doctype"] in FILLED_IN:
        # Nothing to read - something to fill in. The seven days are named for the driver rather
        # than left as blank rows: "last Tuesday" is a question somebody gets wrong, and the
        # statement is worthless if the days it covers are not the days it says.
        today = date.today()
        return {"title": SIGNABLE[held["doctype"]], "format": "prev7",
                "days": [{"on": str(today - timedelta(days=n)), "hours": None}
                         for n in range(7, 0, -1)],
                "version": documents.DRIVER_DOC_VERSION,
                "accountname": held["accountname"],
                "signature": _shown(sig)}
    if held["doctype"] in ON_PAPER:
        # The government's own form, shown as the form. What the driver reads is the page they
        # will sign, not a description of it.
        return {"title": SIGNABLE[held["doctype"]], "format": "pdf",
                "pdf": f"/api/sign/{token}/form.pdf",
                "signedpdf": f"/api/sign/{token}/signed.pdf",
                "asks": ASKS.get(held["doctype"], []),
                "version": documents.DRIVER_DOC_VERSION,
                "accountname": held["accountname"],
                "signature": _shown(sig)}
    doc = documents.fill(documents.driver_document(held["doctype"]), {
        "company": held["accountname"],
        "fullname": f'{held["firstname"]} {held["lastname"]}'.strip(),
    })
    return {"title": SIGNABLE.get(held["doctype"], held["doctype"]), "format": doc.get("format"),
            "text": doc["text"], "version": documents.DRIVER_DOC_VERSION,
            "accountname": held["accountname"],
            # What the signature IS, not only what it looks like: which signature on file this is,
            # whose it is and when it was adopted. A drawn name with nothing behind it is a picture;
            # the stamp is what makes it a signature anybody can check later.
            "signature": {"typedname": sig["typedname"], "fontkey": sig["fontkey"],
                          "recordid": sig["recordid"], "signername": sig["signername"],
                          "adoptedon": str(sig["createdon"]),
                          "ip": sig.get("ip")} if sig else None}


def _keep_document(conn, requestid: str, documentid: str) -> None:
    """Point the request at the signed file, where the column exists.

    Older installations have no `documentid` on a signing request. The signature carries the file
    either way, so a missing column is a convenience lost rather than a record lost."""
    try:
        run(conn, "UPDATE signingrequests SET documentid = :doc WHERE recordid = :id",
            doc=documentid, id=requestid)
    except Exception:                                             # noqa: BLE001 - column absent
        pass


def _recognise(conn: Connection, held: dict, body) -> None:
    """Put a driver who signed before the SSN register existed onto it, now the number is in hand."""
    try:
        signatures.recognise(conn, held["accountid"], "driver", held["driverid"],
                             f'{held["firstname"]} {held["lastname"]}'.strip(), body.ssn, body.dob)
    except ValueError as e:
        raise HTTPException(403, str(e))


def _prove(held: dict, body) -> None:
    """The same check every route makes, against the same record. One copy of it, because three
    routes drifting apart on who may see a Social Security number is not a risk worth taking."""
    if not signatures.valid_ssn(body.ssn):
        raise HTTPException(400, "That Social Security number doesn't look right")
    if (held["ssnhash"] != signatures.ssn_hash(held["accountid"], body.ssn)
            or held["dob"] != body.dob):
        raise HTTPException(403, "Incorrect Date Of Birth / Social Security Combination")


def _shown(sig: dict | None) -> dict | None:
    """What the signature IS, not only what it looks like."""
    if not sig:
        return None
    return {"typedname": sig["typedname"], "fontkey": sig["fontkey"],
            "recordid": sig["recordid"], "signername": sig["signername"],
            "adoptedon": str(sig["createdon"]), "ip": sig.get("ip")}


# What each form needs from the driver before it can be completed. The I-9 asks nothing more here -
# Section 1 is drawn from the application they already filled in. The W-4 asks the one thing the
# IRS requires and nothing it does not: Step 1(c). Steps 2, 3 and 4 are optional on the form
# itself, so they are optional here, and TripProof never guesses a figure on somebody's behalf.
ASKS = {
    "W4": [
        {"id": "filing", "label": "Filing status", "kind": "choice", "required": True,
         "choices": [["single", "Single or married filing separately"],
                     ["joint", "Married filing jointly or qualifying surviving spouse"],
                     ["head", "Head of household"]]},
        {"id": "address1", "label": "Home address", "kind": "text", "required": True},
        {"id": "city", "label": "City or town", "kind": "text", "required": True},
        {"id": "state", "label": "State", "kind": "text", "required": True},
        {"id": "zip", "label": "ZIP code", "kind": "text", "required": True},
        {"id": "twojobs", "label": "I hold more than one job, or I am married filing jointly and "
                                   "my spouse also works", "kind": "tick"},
        {"id": "dependanttotal", "label": "Step 3 - dependants, total claimed", "kind": "money"},
        {"id": "otherincome", "label": "Step 4(a) - other income", "kind": "money"},
        {"id": "deductions", "label": "Step 4(b) - deductions", "kind": "money"},
        {"id": "extrawithholding", "label": "Step 4(c) - extra withholding each pay period",
         "kind": "money"},
    ],
}


def _form_for(conn, held: dict, answers: dict | None, sig: dict | None = None,
              stamp: dict | None = None) -> bytes:
    """The actual government form, filled from what is already known about this driver.

    Built fresh every time it is read and ONCE at the moment of signing. The signed copy is stored
    and served from then on - a form that is rebuilt after signing is a form whose contents could
    have moved under the signature."""
    driver = row(conn, """
        SELECT recordid, firstname, lastname, dob, address1, city, state, zip, email, phone
        FROM drivers WHERE recordid = :d AND accountid = :a
    """, d=held["driverid"], a=held["accountid"]) or {}
    ssn = (phi.get(conn, held["accountid"], "driver", held["driverid"]) or {}).get("ssn")
    # What the driver has typed on this screen, over what is already on their record.
    said = {k: v for k, v in (answers or {}).items() if v not in (None, "")}
    known = {"address1": driver.get("address1"), "city": driver.get("city"),
             "state": driver.get("state"), "zip": driver.get("zip"),
             "email": driver.get("email"), "phone": driver.get("phone")}
    merged = {**{k: v for k, v in known.items() if v}, **said}
    typed = (sig or {}).get("typedname") if sig else None
    face = (sig or {}).get("fontkey", "modern") if sig else "modern"
    if held["doctype"] == "I9":
        app_ = row(conn, """
            SELECT data FROM driverapplications WHERE driverid = :d AND accountid = :a
            ORDER BY startedon DESC LIMIT 1
        """, d=held["driverid"], a=held["accountid"])
        steps = (json.loads((app_ or {}).get("data") or "{}").get("steps") or {})
        merged = {**(steps.get("1") or {}), **merged}
        return i9.build(driver, merged, ssn, signature=typed, fontkey=face, stamp=stamp)
    # The Employers Only row at the foot of the W-4. Nobody signs it, so unlike the I-9's
    # Section 2 it is simply filled from what is on file - and the driver has been hired by the
    # time this form goes out, so the first day of employment is known.
    employer = {**pdfform.company(conn, held["accountid"]),
                "firstday": row(conn, "SELECT hiredon FROM drivers WHERE recordid = :d",
                                d=held["driverid"]).get("hiredon")}
    return w4.build(driver, merged, ssn, signature=typed, fontkey=face, stamp=stamp,
                    employer=employer)


class Preview(Prove):
    answers: dict | None = None


@router.post("/{token}/form.pdf")
def form_pdf(token: str, body: Preview, conn: Connection = Depends(get_conn)):
    """The form as it stands, for the driver to read before they sign it.

    A POST and not a GET, and it proves who is asking. The page carries a date of birth and a
    Social Security number on it: served on a bare token, anybody holding a forwarded link would
    read them. I built it that way first and it was wrong.

    Redrawn from whatever has been typed so far, so what somebody reads is the page they are about
    to sign rather than a half-filled version of it. Unsigned on purpose - a form showing a
    signature before anybody signed it says the thing is done when it is not."""
    held = _open_request(conn, token)
    if held["doctype"] not in ON_PAPER:
        raise HTTPException(404, "That document is not a form")
    _prove(held, body)
    _recognise(conn, held, body)
    return Response(_form_for(conn, held, body.answers), media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=form.pdf"})


@router.post("/{token}/signed.pdf")
def signed_pdf(token: str, body: Prove, conn: Connection = Depends(get_conn)):
    """The finished form, with the entries and the signature on it.

    Shown once it is signed, because the whole point of signing a government form rather than an
    acknowledgement of one is that there is a document at the end of it worth looking at."""
    held = row(conn, """
        SELECT r.recordid, r.accountid, r.driverid, r.doctype, r.documentid, r.signedon,
               d.dob, d.ssnhash
        FROM signingrequests r JOIN drivers d ON d.recordid = r.driverid
        WHERE r.token = :tok
    """, tok=token)
    if not held or not held["signedon"] or not held["documentid"]:
        raise HTTPException(404, "Nothing signed against that link")
    _prove(held, body)
    _recognise(conn, held, body)
    doc = row(conn, "SELECT storagekey FROM documents WHERE recordid = :id",
              id=held["documentid"])
    if not doc:
        raise HTTPException(404, "That file is no longer stored")
    return Response(storage.get(doc["storagekey"]), media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=signed.pdf"})


def _prev7_rows(days: list[dict]) -> list[dict]:
    """The seven days as the driver stated them, checked.

    A blank is not a zero. "I did not work that day" and "I did not answer" look identical on a
    form and mean entirely different things to a carrier working out how many hours it may use,
    so a day left empty is refused rather than counted as nothing."""
    out, seen = [], set()
    for d in days or []:
        try:
            on = date.fromisoformat(str(d.get("on"))[:10])
        except (ValueError, TypeError):
            raise HTTPException(400, "Every day needs a date")
        if on >= date.today() + timedelta(days=1):
            raise HTTPException(400, "A day that has not happened yet cannot be stated")
        if on in seen:
            raise HTTPException(400, f"{on:%m/%d/%Y} is entered twice")
        seen.add(on)
        if d.get("hours") in (None, ""):
            raise HTTPException(400, f"Say how many hours were worked on {on:%m/%d/%Y}, "
                                     "or enter 0 if none")
        try:
            hrs = float(d["hours"])
        except (TypeError, ValueError):
            raise HTTPException(400, "Hours must be a number")
        if hrs < 0 or hrs > 24:
            raise HTTPException(400, "A day holds between 0 and 24 hours")
        out.append({"on": on, "hours": hrs})
    if len(out) != 7:
        raise HTTPException(400, "All seven days have to be stated")
    return sorted(out, key=lambda x: x["on"])


def _prev7_statement(held: dict, days: list[dict], relieved: str | None) -> str:
    """The words that get signed: the driver's own figures, as they submitted them.

    Not a rendition of our wording. A driver signing this is attesting to numbers, so the numbers
    are what is kept with the signature and what its hash is taken over."""
    rows_ = _prev7_rows(days)
    total = sum(r["hours"] for r in rows_)
    lines = "".join(
        f'<tr><td>{r["on"]:%m/%d/%Y}</td><td>{r["hours"]:g} h</td></tr>' for r in rows_)
    name = f'{held["firstname"]} {held["lastname"]}'.strip().title()
    when = str(relieved or "").replace("T", " ")[:16]
    return (f'<p>I, <b>{name}</b>, state that the total time I was ON DUTY during each of the '
            f'7 days immediately preceding today was as shown below, that this includes all '
            f'work for every employer and not only for {escape(held["accountname"])}, and that '
            f'I was last relieved from duty at <b>{escape(when) or "not stated"}</b>. '
            f'49 CFR 395.8(j)(2).</p>'
            f'<table><thead><tr><th>Day</th><th>Total on duty</th></tr></thead>'
            f'<tbody>{lines}</tbody>'
            f'<tfoot><tr><td>Total for the 7 days</td><td>{total:g} h</td></tr></tfoot></table>')


class SignIt(Prove):
    typedname: str | None = None
    fontkey: str = "modern"
    answers: dict | None = None
    # The driver's own figures, where the thing being signed is a form they filled in.
    days: list[dict] | None = None
    relieved: str | None = None


@router.post("/{token}/sign")
def sign_it(token: str, body: SignIt, request: Request, conn: Connection = Depends(get_conn)):
    """Sign it. The signature is the driver's own - the one already on file if they have one, since
    a person signs with one signature - and what is hashed is our copy of the text, not theirs."""
    held = _open_request(conn, token)
    if not signatures.valid_ssn(body.ssn):
        raise HTTPException(400, "That Social Security number doesn't look right")
    if (held["ssnhash"] != signatures.ssn_hash(held["accountid"], body.ssn)
            or held["dob"] != body.dob):
        raise HTTPException(403, "Incorrect Date Of Birth / Social Security Combination")
    name = f'{held["firstname"]} {held["lastname"]}'.strip()
    _recognise(conn, held, body)
    sig = signatures.current(conn, held["accountid"], "driver", held["driverid"])
    if not sig:
        try:
            sig = signatures.adopt(conn, held["accountid"], "driver", held["driverid"], name,
                                   body.typedname or name, body.fontkey, "dob_ssn",
                                   client_ip(request), request.headers.get("user-agent"),
                                   ssn=body.ssn, dob=body.dob)
        except ValueError as e:
            raise HTTPException(400, str(e))
    if held["doctype"] in FILLED_IN:
        # What gets signed is what the driver entered. The days are written to the same table
        # the office's own entries go into - one record of the driver's work, not two that
        # disagree - marked as having come from the driver, and the words signed are the
        # figures themselves so the signature can be checked against them later.
        text = _prev7_statement(held, body.days or [], body.relieved)
        signatures.sign(conn, held["accountid"], sig["recordid"], held["doctype"],
                        held["driverid"], text, version=documents.DRIVER_DOC_VERSION,
                        ip=client_ip(request), useragent=request.headers.get("user-agent"))
    elif held["doctype"] in ON_PAPER:
        # The signed form is built once, here, and kept. The hash is of the FILE, because that is
        # what was signed - there is no text behind it to hash.
        recordid = newid()
        pdf = _form_for(conn, held, body.answers, sig,
                        stamp={"recordid": recordid, "signedon": str(utcnow()),
                               "ip": client_ip(request)})
        documentid = storage.keep(conn, held["accountid"], "documents", pdf,
                                  f'{held["doctype"].lower()}-{name.lower().replace(" ", "-")}.pdf',
                                  "application/pdf", None, origin=storage.DRIVER)
        signatures.sign(conn, held["accountid"], sig["recordid"], held["doctype"],
                        held["driverid"], "", version=documents.DRIVER_DOC_VERSION,
                        contenthash=hashlib.sha256(pdf).hexdigest(), recordid=recordid,
                        ip=client_ip(request), useragent=request.headers.get("user-agent"))
        _keep_document(conn, held["recordid"], documentid)
    else:
        doc = documents.fill(documents.driver_document(held["doctype"]),
                             {"company": held["accountname"], "fullname": name})
        signatures.sign(conn, held["accountid"], sig["recordid"], held["doctype"],
                        held["driverid"], doc["text"], version=documents.DRIVER_DOC_VERSION,
                        ip=client_ip(request), useragent=request.headers.get("user-agent"))
    run(conn, "UPDATE signingrequests SET signedon = :now WHERE recordid = :id",
        now=utcnow(), id=held["recordid"])
    log(conn, None, "signed-on-request", "driver", held["driverid"], {"doctype": held["doctype"]},
        ip=client_ip(request), accountid=held["accountid"])
    events.record(conn, held["accountid"], "driver", held["driverid"], "signed", held["doctype"],
                  label=f'{name.title()} signed the {SIGNABLE[held["doctype"]]}')
    # The I-9 and the W-4 go out together, so finishing one hands over the other rather than
    # leaving somebody to go and find a second email. Only an outstanding request of THEIRS, and
    # only one that is still live.
    nxt = _still_owed(conn, held["accountid"], held["driverid"], held["recordid"])
    saved(conn)
    return {"ok": True, "title": SIGNABLE.get(held["doctype"], held["doctype"]),
            "accountname": held["accountname"],
            "onpaper": held["doctype"] in ON_PAPER,
            "token": token,
            "next": {"token": nxt["token"],
                     "title": SIGNABLE.get(nxt["doctype"], nxt["doctype"])} if nxt else None}
