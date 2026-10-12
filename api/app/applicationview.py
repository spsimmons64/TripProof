###################################################################################################
# The driver's application, as one page of HTML.
#
# Everything the applicant entered, everything they signed, and every file they uploaded, in one
# self-contained document: attachments are embedded as data URIs, so the page can be saved, mailed
# or printed and still be complete. Nothing here reads from the network.
#
# The HTML is built on the server so the same copy can later be printed, stored against the driver,
# or handed to an auditor - the portal only displays it.
###################################################################################################
import base64
import io
import json
from datetime import date, datetime
from functools import lru_cache
from html import escape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from sqlalchemy.engine import Connection

from app import documents, signatures, storage
from app.db import row, rows

# A file bigger than this is named but not carried, so one enormous upload cannot make the page
# unusable. Nothing we accept from the application is close: the limit there is 15 MB.
MAX_EMBED = 12 * 1024 * 1024

# A photograph of a licence comes off a phone at several megapixels, and every byte of it is
# base64 in the page. An exhibit is shown, and printed, about seven inches wide; this is more than
# that needs at print resolution, and turns six megabytes of camera JPEG into a few hundred
# kilobytes. The stored file is untouched - only the copy carried in the page is resized.
EXHIBIT_PX = 1800
_FITTED: dict[str, bytes] = {}

# What each exhibit is, said as what it actually is: a copy the applicant supplied, not the
# original instrument.
UPLOAD_LABELS = {
    "license_front": "Copy of the front of the driver's license",
    "license_back": "Copy of the back of the driver's license",
    "medical_certificate": "Copy of the driver's medical certificate",
    "license_action": "Documentation of license revocation or denial",
    "i9_document": "Form I-9 supporting document",
}

DOC_TITLES = {
    "APPLICATION": "Application for employment",
    "DRUG_POLICY": "Drug and alcohol policy",
    "PHI_ACK": "PHI confidentiality and privacy acknowledgment",
    "WORKPLACE_POLICY": "Workplace policy",
    "FCRA_SUMMARY": "A summary of your rights under the Fair Credit Reporting Act",
    "FCRA_AUTH": "Disclosure and authorization for employment background check",
    "CLEARINGHOUSE_CONSENT": "FMCSA Clearinghouse limited query consent",
    "SAFETY_PERFORMANCE_CONSENT": "Consent to release safety performance history",
    "I9": "Form I-9, Employment Eligibility Verification",
    "W4": "Form W-4",
    # Missing from here, a signed sheet prints its own CODE as its heading - and now as its
    # filename inside the downloaded driver file too. Every doctype in signatures.DOC_TYPES
    # needs a line here; these three were each found by somebody reading PREV7_ONDUTY or
    # PREEMP_DA_QUESTIONNAIRE off a document that was meant to be handed to an auditor.
    "PREV7_ONDUTY": "Previous 7 Days' On-Duty Hours Statement",
    "PREEMP_DA_QUESTIONNAIRE": "Pre-employment drug and alcohol questionnaire",
    "ANNUAL_REVIEW": "Annual review of driving record",
}


def _t(value) -> str:
    """Anything at all, as text fit to put on the form."""
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return value.strftime("%m/%d/%Y %H:%M UTC")
    if isinstance(value, date):
        return value.strftime("%m/%d/%Y")
    text = str(value)
    if len(text) == 10 and text[4] == "-" and text[7] == "-":      # YYYY-MM-DD
        return f"{text[5:7]}/{text[8:10]}/{text[0:4]}"
    if text in ("yes", "no"):
        return text.capitalize()
    return text


def _blank(label: str, value, span: int = 3) -> str:
    """A ruled blank with its caption underneath, the way a printed form reads: what was written
    sits on the line, the line is named below it."""
    return (f'<div class="blank s{span}"><span class="avval">{escape(_t(value)) or "&nbsp;"}</span>'
            f'<span class="avcap">{escape(label)}</span></div>')


def _note(label: str, value, span: int = 12) -> str:
    """A blank for something written at length: it wraps and grows rather than sitting on one rule."""
    return (f'<div class="blank note s{span}"><span class="avval">{escape(_t(value)) or "&nbsp;"}</span>'
            f'<span class="avcap">{escape(label)}</span></div>')


def _box(label: str, answer, options=("yes", "no")) -> str:
    """A question with boxes to tick, as the paper form has."""
    ticks = "".join(
        f'<span class="tick">{"&#9746;" if str(answer).lower() == o else "&#9744;"} {o.capitalize()}</span>'
        for o in options)
    return f'<div class="question"><span class="q">{escape(label)}</span><span class="ticks">{ticks}</span></div>'


def _rows(headings: list[tuple[str, int]], body: list[list], least: int = 3) -> str:
    """A ruled grid. Empty lines are kept so the form looks like a form, not a report."""
    head = "".join(f'<th style="width:{w}%">{escape(h)}</th>' for h, w in headings)
    out = []
    for r in body:
        out.append("<tr>" + "".join(f"<td>{escape(_t(c)) or '&nbsp;'}</td>" for c in r) + "</tr>")
    for _ in range(max(0, least - len(body))):
        out.append("<tr>" + "<td>&nbsp;</td>" * len(headings) + "</tr>")
    return f'<table class="ruled"><thead><tr>{head}</tr></thead><tbody>{"".join(out)}</tbody></table>'


def _letterhead(company: str, title: str = "", left: str = "", right: str = "") -> str:
    """Whose file this is, at the top of the page.

    A document out of its folder is anonymous - a consent form looks the same for every company in
    the country - so every sheet says which company holds it before it says anything else. It is
    the same letterhead the application prints, so a page pulled from either reads the same way."""
    filed = (f'<div class="filed"><span>{escape(left)}</span><span>{escape(right)}</span></div>'
             if left or right else "")
    head = f'<h1>{escape(title)}</h1>' if title else ''
    return (f'<div class="letterhead"><div class="co">{escape(company or "")}</div>'
            f'{head}{filed}</div>')


def _section(title: str, body: str) -> str:
    return f'<div class="section"><div class="bar">{escape(title)}</div>{body}</div>'


def _attachment(conn: Connection, accountid: str, kind: str, upload: dict, n: int) -> str:
    """One uploaded file, on a sheet of its own like an exhibit attached to the application."""
    label = UPLOAD_LABELS.get(kind, kind.replace("_", " ").capitalize())
    doc = row(conn, """
        SELECT filename, mimetype, bytes, sha256, storagekey FROM documents
        WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=upload.get("documentid"), a=accountid)
    head = (f'<div class="exhibit"><span class="label">Exhibit {chr(64 + n)}</span>'
            f'<span class="name">{escape(label)}</span></div>')
    if not doc:
        return f'<div class="sheet">{head}<p class="none">The file is no longer on file.</p></div>'
    meta = f'{doc["filename"]} · {doc["bytes"]:,} bytes · SHA-256 {doc["sha256"][:16]}…'
    try:
        blob = storage.get(doc["storagekey"])
    except storage.Missing:
        return f'<div class="sheet">{head}<p class="none">{escape(meta)} is no longer stored.</p></div>'
    if len(blob) > MAX_EMBED:
        return f'<div class="sheet">{head}<p class="none">{escape(meta)} is too large to carry in this page.</p></div>'
    blob, mime = _fit(blob, doc["mimetype"] or "application/octet-stream", doc["sha256"])
    data = f"data:{mime};base64,{base64.b64encode(blob).decode()}"
    shown = (f'<img src="{data}" alt="{escape(label)}">' if mime.startswith("image/")
             else f'<embed src="{data}#toolbar=0&navpanes=0&scrollbar=0&view=FitH" '
                  f'type="{mime}">' if mime == "application/pdf" else "")
    # The save link takes its file from what is already on the sheet (the portal wires it up on
    # display); repeating the data URI in an href would carry every exhibit twice.
    return (f'<div class="sheet">{head}<div class="pasted">{shown}</div>'
            f'<p class="meta">{escape(meta)} · '
            f'<a class="avsave" data-name="{escape(doc["filename"])}">save</a></p></div>')


def _fit(blob: bytes, mime: str, sha: str | None = None) -> tuple[bytes, str]:
    """An image no wider than EXHIBIT_PX, as (bytes, mime). Anything that is not an image, or that
    will not open, comes back exactly as it went in."""
    if not mime.startswith("image/"):
        return blob, mime
    if sha and sha in _FITTED:
        return _FITTED[sha], "image/jpeg"
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(blob)))
        if image.width <= EXHIBIT_PX and len(blob) <= 600 * 1024:
            return blob, mime
        if image.width > EXHIBIT_PX:
            image = image.resize((EXHIBIT_PX, round(image.height * EXHIBIT_PX / image.width)),
                                 Image.LANCZOS)
        # Photographs of a licence have no transparency to keep, and JPEG is a third of the size.
        out = io.BytesIO()
        image.convert("RGB").save(out, format="JPEG", quality=82, optimize=True, progressive=True)
        small = out.getvalue()
    except Exception:
        return blob, mime
    if len(small) >= len(blob):
        return blob, mime
    if sha:
        if len(_FITTED) > 32:
            _FITTED.clear()
        _FITTED[sha] = small
    return small, "image/jpeg"


def _fullname_of(driver: dict) -> str:
    return f"{driver.get('firstname') or ''} {driver.get('lastname') or ''}".strip().title()


def _markdown(text: str) -> str:
    """The plain documents are Markdown, with only headings, bullets and bold in them."""
    out = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#"):
            out.append(f"<h3>{escape(block.lstrip('#').strip())}</h3>")
        elif block.startswith("- "):
            items = "".join(f"<li>{_bold(i.lstrip('- ').strip())}</li>" for i in block.split("\n- "))
            out.append(f"<ul>{items}</ul>")
        else:
            out.append(f"<p>{_bold(block)}</p>")
    return "".join(out)


def _bold(text: str) -> str:
    parts = escape(text.replace("\n", " ")).split("**")
    return "".join(p if i % 2 == 0 else f"<b>{p}</b>" for i, p in enumerate(parts))


def _company_policy(conn: Connection, accountid: str, code: str) -> dict | None:
    """The most recent copy of one of the company's own policies, as the application showed it."""
    return row(conn, """
        SELECT d.filename, d.mimetype, d.bytes, d.sha256, d.storagekey
        FROM credentials c
        JOIN credentialtypes t ON t.recordid = c.credentialtypeid
        JOIN documents d ON d.recordid = c.documentid
        WHERE c.accountid = :a AND t.code = :code AND c.subject = 'company'
          AND c.revokedon IS NULL AND c.deleted IS NULL AND d.deleted IS NULL
        ORDER BY COALESCE(c.issuedon, DATE(c.added)) DESC, c.added DESC LIMIT 1
    """, a=accountid, code=code)


def _embedded(blob: bytes, mime: str, alt: str) -> str:
    if len(blob) > MAX_EMBED:
        return '<p class="none">This copy is too large to carry in the page.</p>'
    blob, mime = _fit(blob, mime)
    data = f"data:{mime};base64,{base64.b64encode(blob).decode()}"
    if mime.startswith("image/"):
        return f'<div class="pasted"><img src="{data}" alt="{escape(alt)}"></div>'
    # The document itself, with none of the reader's own furniture around it: this is something
    # to read, not to operate. `view=FitH` fits the page to the width it has been given - without
    # it the reader picks its own zoom and letterboxes a portrait page inside black gutters, which
    # reads as a broken frame rather than as a document.
    return (f'<div class="pasted"><embed src="{data}#toolbar=0&navpanes=0&scrollbar=0&view=FitH" '
            f'type="{mime}"></div>')


# The hand a signature is drawn in, as a file the server can draw with.
SIGNATURE_FACES = {"modern": "ms-madi.ttf", "signature": "meddon.ttf", "quick": "kristi.ttf",
                   "hand": "zeyada.ttf", "cursive": "cedarville-cursive.ttf",
                   "fine": "herr-von-muellerhoff.ttf", "bold": "style-script.ttf"}
SIGNATURE_INK = (15, 58, 67)
SIGNATURE_PX = 132          # drawn large and shown small, so it stays sharp in print


@lru_cache(maxsize=256)
def signature_image(typedname: str, fontkey: str) -> str:
    """The signature drawn as an image. A web font cannot be relied on wherever this page ends up -
    printed, mailed, or rendered to PDF - but a picture of the signature travels with it."""
    face = SIGNATURE_FACES.get(fontkey, SIGNATURE_FACES["modern"])
    path = Path(__file__).resolve().parent / "legal" / "forms" / face
    font = ImageFont.truetype(str(path), SIGNATURE_PX)
    box = font.getbbox(typedname)
    pad = SIGNATURE_PX // 6
    image = Image.new("RGBA", (box[2] - box[0] + pad * 2, box[3] - box[1] + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(image).text((pad - box[0], pad - box[1]), typedname, font=font, fill=SIGNATURE_INK + (255,))
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return f"data:image/png;base64,{base64.b64encode(out.getvalue()).decode()}"


def _signature_block(sig: dict, label: str = "Signature of driver") -> str:
    """The signature on its rule at the left, the date it was signed on its own rule at the right,
    and one line of audit stamp under the signature."""
    # Everything that proves the signing, on one line under it: who signed, which signature on file
    # it was, and when and from where it was used.
    stamp = " · ".join(filter(None, [
        "Signed electronically", sig.get("signername"), sig["recordid"], _t(sig["signedon"]),
        f'IP {sig["ip"] or "not recorded"}',
    ]))
    return ('<div class="avrow">'
            '<div class="avline">'
            f'<span class="avwritten"><img class="avsig" alt="{escape(sig["typedname"])}"'
            f' src="{signature_image(sig["typedname"], sig["fontkey"])}"></span>'
            f'<span class="avcap">{escape(label)}</span></div>'
            f'<div class="avline avshort"><span class="avval">{_t(sig["signedon"].date())}</span>'
            '<span class="avcap">Date signed</span></div></div>'
            f'<p class="avstamp">{escape(stamp)}</p>')


# The company's own policies: the driver is given them and signs for them, so the file itself is
# not reprinted in the application - an affidavit of receipt stands in its place.
AFFIDAVIT = {"DRUG_POLICY": "Drug And Alcohol Policy", "WORKPLACE_POLICY": "Workplace Policy",
             "PHI_ACK": "PHI Confidentiality And Privacy Acknowledgment"}
# The company credential each of those is filed under, when the company has filed one.
POLICY_CODES = {"DRUG_POLICY": "DRUG_ALCOHOL_POLICY", "WORKPLACE_POLICY": "WORKPLACE_POLICY",
                "PHI_ACK": "PHI_POLICY"}


def _affidavit(conn: Connection, accountid: str, doctype: str, sig: dict, company: str,
               fullname: str) -> str:
    """Not the policy, but a sworn record that the driver received it and signed for it."""
    name = AFFIDAVIT.get(doctype, DOC_TITLES.get(doctype, doctype.replace("_", " ").title()))
    code = POLICY_CODES.get(doctype)
    policy = _company_policy(conn, accountid, code) if code else None
    filed = (f'<p class="filedcopy">The copy given was <b>{escape(policy["filename"])}</b>, '
             f'{policy["bytes"]:,} bytes, SHA-256 {escape(policy["sha256"])}.</p>' if policy else
             f'<p class="filedcopy">The wording published by {escape(company)} at the time of signing.</p>')
    return (f'<div class="exhibit"><span class="label">Affidavit</span>'
            f'<span class="name">Receipt of the {escape(name)}</span></div>'
            f'<div class="affidavit">'
            f'<p>I, <b>{escape(fullname)}</b>, declare that I have received a copy of the '
            f'<b>{escape(name)}</b> of <b>{escape(company)}</b>, that I have read it and understand it, '
            f'that I have had the opportunity to ask questions about it, and that I agree to follow it '
            f'for as long as I drive for the company.</p>'
            f'{filed}</div>'
            f'<div class="section certify">{_signature_block(sig)}</div>')


def _signed_sheet(conn: Connection, accountid: str, doctype: str, sig: dict, blanks: dict, data: dict) -> str:
    """One signed document on a sheet of its own: what was signed, then the signature under it."""
    title = DOC_TITLES.get(doctype, doctype)
    body = ""
    # The consents are shown as the file the account filed, where it filed one.
    policy_code = {"FCRA_AUTH": "FCRA_CONSENT"}.get(doctype)
    policy = _company_policy(conn, accountid, policy_code) if policy_code else None
    if doctype == "I9":
        kept = (data.get("signeddocs") or {}).get("I9")
        doc = row(conn, "SELECT filename, mimetype, storagekey FROM documents WHERE recordid = :id",
                  id=(kept or {}).get("documentid")) if kept else None
        if doc:
            try:
                body = _embedded(storage.get(doc["storagekey"]), doc["mimetype"] or "application/pdf", title)
            except storage.Missing:
                body = '<p class="none">The signed form is no longer stored.</p>'
    elif policy:
        try:
            body = _embedded(storage.get(policy["storagekey"]), policy["mimetype"] or "application/pdf", title)
        except storage.Missing:
            body = '<p class="none">The filed copy is no longer stored.</p>'
    # The words that were actually signed, where they were kept. A document whose blanks fill from
    # live data cannot be rebuilt once that data moves - appoint a new DER and this would print the
    # new name over an old signature. The stored copy outranks anything re-rendered.
    if not body and sig.get("signedtext"):
        body = f'<div class="doc">{sig["signedtext"]}</div>'
    if not body:
        try:
            doc = documents.fill(documents.driver_document(doctype), blanks)
            body = (f'<div class="doc">{doc["text"]}</div>' if doc.get("format") == "html"
                    else f'<div class="doc">{_markdown(doc["text"])}</div>')
        except KeyError:
            body = '<p class="none">This document is no longer published.</p>'
    signed = f'Signed {_t(sig.get("signedon"))}' if sig.get('signedon') else 'Not signed'
    return (f'<div class="sheet">'
            f'{_letterhead(blanks.get("company", ""), title, blanks.get("fullname", ""), signed)}'
            f'{body}<div class="section certify">{_signature_block(sig)}</div></div>')


def build(conn: Connection, accountid: str, company: str, driver: dict, app_: dict,
          formonly: bool = False) -> str:
    """The whole application as printed sheets, or - for someone asking to read the application
    itself - the form and its certification alone, without the documents and exhibits behind it."""
    data = json.loads(app_["data"] or "{}")
    steps = data.get("steps") or {}
    one = steps.get("1") or {}
    two = steps.get("2") or {}
    signed = signatures.signed(conn, accountid, driver["recordid"])
    sig = signed.get("APPLICATION")

    head = (f'<div class="letterhead"><div class="co">{escape(company)}</div>'
            f'<h1>Application For Employment</h1>'
            f'<div class="filed">'
            f'<span>{escape(_fullname_of(driver))}</span>'
            f'<span>{"Submitted " + _t(app_["submittedon"]) if app_.get("submittedon") else "Not submitted"}</span>'
            f'</div></div>')

    applicant = _section("Applicant", (
        '<div class="fields">'
        + _blank("Last name (family name)", one.get("lastname") or driver["lastname"], 4)
        + _blank("First name (given name)", one.get("firstname") or driver["firstname"], 4)
        + _blank("M.I.", one.get("middleinitial"), 1)
        + _blank("Date of birth", driver.get("dob"), 3)
        + _blank("Street address", one.get("address1"), 8)
        + _blank("Apt / suite", one.get("apt"), 4)
        + _blank("City", one.get("city"), 5)
        + _blank("State", one.get("state"), 2)
        + _blank("ZIP code", one.get("zip"), 5)
        + _blank("Primary telephone", one.get("phone"), 4)
        + _blank("Secondary telephone", one.get("phone2"), 4)
        + _blank("Email address", one.get("email"), 4)
        + _blank("Emergency contact", one.get("emergencyname"), 6)
        + _blank("Emergency telephone", one.get("emergencyphone"), 6)
        + "</div>"))

    commercial = _section("Commercial Driving And Medical Certification", (
        _box("Are you exempt from possessing a medical certificate?", two.get("medexempt"))
        + '<div class="fields">'
        + _blank("Medical card issued", two.get("medissued"), 6)
        + _blank("Medical card expires", two.get("medexpires"), 6)
        + "</div>"))

    residences = _section("Residence History - Previous Three Years", _rows(
        [("Street address", 45), ("City", 25), ("State", 10), ("ZIP code", 20)],
        [[r.get("address1"), r.get("city"), r.get("state"), r.get("zip")] for r in (one.get("residences") or [])]))

    employers = one.get("employers") or []
    gaps = one.get("gaps") or {}
    # Each employer reads like the applicant block: ruled blanks under a heading of its own.
    blocks = []
    for n, e in enumerate(employers, start=1):
        blocks.append(f'<div class="subhead">Employer {n}</div><div class="fields">'
                      + _blank("Employer", e.get("employer"), 5)
                      + _blank("Supervisor", e.get("supervisor"), 4)
                      + _blank("Telephone", e.get("phone"), 3)
                      + _blank("Address", e.get("address1"), 6)
                      + _blank("City", e.get("city"), 3)
                      + _blank("State", e.get("state"), 1)
                      + _blank("ZIP code", e.get("zip"), 2)
                      + _blank("Email address", e.get("email"), 6)
                      + _blank("From", e.get("from"), 3)
                      + _blank("Through", e.get("through"), 3)
                      + _blank("Subject to DOT/FMCSA regulations", e.get("dotregulated"), 6)
                      + _blank("Safety-sensitive function", e.get("safetysensitive"), 6)
                      + "</div>")
    if not employers:
        blocks.append('<div class="fields"><p class="none">No employers given.</p></div>')
    for key, why in gaps.items():
        start_, _, end_ = key.partition("_")
        # The dates head the block; the reason is given the room a real answer needs.
        blocks.append(f'<div class="subhead">Explained gap in employment · {escape(_t(start_))} to '
                      f'{escape(_t(end_))}</div><div class="fields">'
                      + _note("Reason given", why) + "</div>")
    employment = _section("Employment History", "".join(blocks))

    licences = _section("Driver's Licenses Held", _rows(
        [("License number", 26), ("State", 10), ("Class", 10), ("Issued", 14), ("Expires", 14), ("Endorsements", 26)],
        [[l.get("number"), l.get("state"), l.get("classification"), l.get("issued"), l.get("expires"),
          ", ".join(l.get("endorsements") or [])] for l in (two.get("licenses") or [])], least=2))

    accidents = _section("Accidents And Crashes - Previous Three Years", _rows(
        [("Date", 14), ("Location", 40), ("Injuries", 10), ("Fatalities", 10), ("Hazmat", 13), ("At fault", 13)],
        [[a.get("date"), a.get("location"), a.get("injuries") or 0, a.get("fatalities") or 0,
          bool(a.get("hazmat")), bool(a.get("atfault"))] for a in (two.get("accidents") or [])], least=2))

    violations = _section("Moving Traffic Violations - Previous Three Years", _rows(
        [("Date", 16), ("Location", 44), ("Violation", 40)],
        [[v.get("date"), v.get("location"), v.get("violation")] for v in (two.get("violations") or [])], least=2))

    action = _section("License Revocation Or Denial", (
        _box("Has your license ever been revoked, or have you ever been denied a license, in the last 3 years?",
             two.get("licenseaction"))
        + '<div class="fields">' + _blank("If yes, please explain", two.get("licenseactionwhy"), 12) + "</div>"))

    certification = (
        '<div class="section certify"><div class="bar">Certification</div>'
        '<p>This certifies that this application was completed by me, and that all entries on it and'
        ' information in it are true and complete to the best of my knowledge.</p>'
        + (_signature_block(sig, "Signature of applicant") if sig else "")
        + "</div>")

    sheet = (f'<div class="sheet">{head}{applicant}{commercial}{residences}{employment}{licences}'
             f'{accidents}{violations}{action}{certification}</div>')

    # Every document they signed, each one shown as they saw it with their signature beneath it.
    licences_held = two.get("licenses") or []
    cdl = next((l for l in licences_held if l.get("classification") in ("A", "B", "C")), None) or \
        (licences_held[0] if licences_held else {})
    blanks = {"company": company.upper(),
              "fullname": f"{driver['firstname']} {driver['lastname']}".strip().upper(),
              "cdlstate": (cdl.get("state") or "").upper(), "cdlnumber": (cdl.get("number") or "").upper(),
              "dob": _t(driver.get("dob"))}
    order = ["DRUG_POLICY", "WORKPLACE_POLICY", "CLEARINGHOUSE_CONSENT", "SAFETY_PERFORMANCE_CONSENT",
             "FCRA_SUMMARY", "FCRA_AUTH", "I9", "W4"]
    # The two policy affidavits share a sheet; everything else gets one of its own.
    affidavits = "".join(_affidavit(conn, accountid, d, signed[d], company, blanks["fullname"])
                         for d in AFFIDAVIT if d in signed)
    affidavit_sheet = f'<div class="sheet affidavits">{affidavits}</div>' if affidavits else ""
    signed_sheets = affidavit_sheet + "".join(
        _signed_sheet(conn, accountid, d, signed[d], blanks, data)
        for d in order if d in signed and d not in AFFIDAVIT)

    uploads = data.get("uploads") or {}
    exhibits = "".join(_attachment(conn, accountid, kind, up, n)
                       for n, (kind, up) in enumerate(uploads.items(), start=1))
    return sheet if formonly else sheet + signed_sheets + exhibits


# The look of the form, served with it so a saved copy and the portal show the same paper. Every
# rule is scoped to .appview, which is the class on the portal's panel and on a saved page's body.
STYLE = """
/* The sheets sit on a solid dark ground, so white paper reads as paper. */
.appview { background: #0f3a43; padding: 22px 16px; }
.appview .sheet { width: 8.5in; max-width: 100%; margin: 0 auto 26px; background: #fff; padding: 0.5in 0.55in;
  border-top: 5px solid #1c6979;
  box-shadow: 0 2px 4px rgb(0 0 0 / 22%), 0 18px 38px rgb(0 0 0 / 28%);
  font-family: Inter, system-ui, -apple-system, 'Segoe UI', sans-serif; color: #13272b; font-size: 12.5px;
  line-height: 1.45; }
.appview .letterhead { margin-bottom: 20px; }
.appview .letterhead .co { font-size: 12px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase;
  color: #1c6979; }
.appview .letterhead h1 { font-size: 26px; margin: 2px 0 10px; letter-spacing: -.01em; color: #0f3a43;
  font-weight: 800; text-transform: capitalize; }
.appview .letterhead h1::before { content: none; }
.appview .letterhead .filed { display: flex; justify-content: space-between; gap: 16px; font-size: 11px;
  letter-spacing: .04em; text-transform: uppercase; color: #4b5c60; border-top: 2px solid #ffa52f;
  padding-top: 8px; }
.appview .sheet, .appview .sheet td, .appview .sheet p, .appview .sheet li { color: #13272b; }

.appview .section { margin: 0 0 18px; break-inside: avoid; }
.appview .bar { background: #0f3a43; color: #fff; font-size: 11px; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; padding: 5px 10px; border-radius: 4px 4px 0 0; }
.appview .subhead { font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  color: #1c6979; margin: 14px 0 6px; }
/* A block of blanks under its own heading closes itself, rather than hanging from a section bar. */
.appview .subhead + .fields { border-top: 1px solid #dfe6e7; border-radius: 6px; }
/* And the same where a sentence sits between the bar and the blanks: the box is drawn open at the
   top so it can hang from the bar, so anything in between leaves it with no lid. */
.appview .section p + .fields { border-top: 1px solid #dfe6e7; border-radius: 6px; }

.appview .fields { display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px 14px;
  padding: 14px 12px 10px; border: 1px solid #dfe6e7; border-top: none; border-radius: 0 0 6px 6px; }
.appview .blank { display: flex; flex-direction: column; }
.appview .blank .avval { border-bottom: 1px solid #b9cbd0; min-height: 20px; font-size: 13.5px; font-weight: 600;
  color: #0f3a43; padding: 0 2px 2px; overflow-wrap: anywhere; }
/* Written at length: it wraps, keeps the line breaks it was given, and grows with what is in it. */
.appview .blank.note .avval { font-weight: 500; font-size: 12.5px; line-height: 1.55; white-space: pre-wrap;
  min-height: 34px; padding-bottom: 6px; }
.appview .blank .avcap { font-size: 9.5px; text-transform: uppercase; letter-spacing: .05em; color: #74858a;
  padding-top: 3px; }
.appview .s1 { grid-column: span 1; } .appview .s2 { grid-column: span 2; } .appview .s3 { grid-column: span 3; }
.appview .s4 { grid-column: span 4; } .appview .s5 { grid-column: span 5; } .appview .s6 { grid-column: span 6; }
.appview .s8 { grid-column: span 8; } .appview .s12 { grid-column: span 12; }

.appview .question { display: flex; justify-content: space-between; align-items: baseline; gap: 16px;
  padding: 9px 12px; border-left: 1px solid #dfe6e7; border-right: 1px solid #dfe6e7;
  border-bottom: 1px solid #eef2f3; }
.appview .question:last-child { border-bottom: 1px solid #dfe6e7; border-radius: 0 0 6px 6px; }
.appview .ticks { white-space: nowrap; }
.appview .tick { margin-left: 16px; font-size: 13px; color: #1c6979; font-weight: 600; }

.appview table.ruled { width: 100%; border-collapse: collapse; }
.appview table.ruled th { background: #eef6f8; color: #1c6979; border: 1px solid #dfe6e7; font-size: 9.5px;
  text-transform: uppercase; letter-spacing: .05em; padding: 6px 8px; text-align: left; }
.appview table.ruled td { border: 1px solid #eef2f3; padding: 7px 8px; font-size: 12px; height: 20px;
  overflow-wrap: anywhere; }
.appview table.ruled tr:nth-child(even) td { background: #fafcfc; }

.appview .certify p, .appview .affidavit p { margin: 10px 2px; font-size: 12.5px; }
.appview .affidavit { border: 1px solid #dfe6e7; border-left: 4px solid #ffa52f; border-radius: 6px;
  padding: 14px 16px; margin-bottom: 6px; background: #fffdf9; }
/* Two affidavits to a sheet, the second set off from the first. */
.appview .affidavits .exhibit + .affidavit { margin-top: 0; }
.appview .affidavits .certify { margin-bottom: 30px; }
.appview .affidavits .exhibit { margin-top: 26px; }
.appview .affidavits > .exhibit:first-child { margin-top: 0; }
.appview .affidavit .filedcopy { font-size: 10.5px; color: #4b5c60; margin-top: 12px; overflow-wrap: anywhere; }

/* The signature sits left with its stamp beside it; the date is always to the right. */
.appview .avrow { display: flex; gap: 28px; align-items: flex-end; padding: 16px 2px 0; }
.appview .avline { flex: 1; display: flex; flex-direction: column; }
.appview .avline.avshort { flex: 0 0 190px; }
/* The name stays on one line so the signature rule and the date rule line up with each other. */
.appview .avline .avwritten { display: flex; align-items: flex-end; border-bottom: 1px solid #b9cbd0;
  height: 44px; padding: 0 2px 2px; }
.appview .avline .avval { border-bottom: 1px solid #b9cbd0; height: 44px; display: flex; align-items: flex-end;
  padding: 0 2px 6px; font-size: 13.5px; font-weight: 600; color: #0f3a43; }
/* The signature is a picture of itself, so it looks the same on screen, in print and in the PDF. */
.appview .avline .avsig { height: 34px; width: auto; display: block; }
/* One quiet line under the signature: who signed, which signature it was, and when and from
   where it was used. */
/* Named with its element so the paragraph rules above cannot pull it back to body size. */
.appview .sheet p.avstamp { font-size: 8px; line-height: 1.6; color: #a9b6ba; margin: 7px 2px 0;
  letter-spacing: .01em; overflow-wrap: anywhere; }
.appview .avline .avcap { font-size: 9.5px; text-transform: uppercase; letter-spacing: .05em; color: #74858a;
  padding-top: 3px; }

.appview .none { font-size: 12px; color: #74858a; }
/* The chip and the name share a line: centred on each other, not sat on a shared baseline, which
   is what put them out of true once the chip had padding of its own. */
.appview .exhibit { display: flex; align-items: center; gap: 12px; border-bottom: 2px solid #ffa52f;
  padding-bottom: 9px; margin-bottom: 16px; }
.appview .exhibit .label { font-size: 10px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase;
  color: #fff; background: #1c6979; padding: 4px 9px 3px; border-radius: 3px; line-height: 1; }
.appview .exhibit .name { font-size: 14px; font-weight: 600; color: #0f3a43; line-height: 1; }
.appview .pasted { text-align: center; }
.appview .pasted img { max-width: 100%; border: 1px solid #dfe6e7; border-radius: 4px; }
.appview .pasted embed { width: 100%; height: 9in; border: 1px solid #dfe6e7; border-radius: 4px; }
.appview .meta { font-size: 10px; color: #74858a; margin-top: 10px; overflow-wrap: anywhere; }
.appview .avsave { color: #1c6979; font-weight: 600; cursor: pointer; text-decoration: underline; }

.appview .doc { font-size: 12.5px; }
.appview .doc h2 { font-size: 16px; text-align: center; margin: 0 0 14px; color: #0f3a43; }
.appview .doc h3 { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: #1c6979;
  margin: 16px 0 6px; }
.appview .doc p { margin: 0 0 9px; }
.appview .doc ul { margin: 0 0 9px; padding-left: 20px; }
.appview .doc li { margin-bottom: 5px; }
.appview .doc table { width: 100%; border-collapse: collapse; font-size: 11px; margin: 10px 0; }
.appview .doc th, .appview .doc td { border: 1px solid #dfe6e7; padding: 6px; text-align: left;
  vertical-align: top; }
.appview .doc th { background: #eef6f8; color: #1c6979; }
.appview .doc .blank { display: inline-block; min-width: 220px; border-bottom: 1px solid #b9cbd0; padding: 0 6px;
  font-weight: 700; color: #0f3a43; }
.appview .doc .spanish { font-style: italic; text-align: center; font-size: 11px; color: #4b5c60; }
.appview .doc .smallcaps { font-variant: small-caps; font-weight: 700; }
.appview .doc .small { font-size: 10.5px; color: #4b5c60; }

@media print {
  .appview { background: #fff; padding: 0; }
  .appview .sheet { box-shadow: none; margin: 0; page-break-after: always; width: auto; }
}
"""


PRINT_CSS = """
@page { size: Letter; margin: 0.45in 0.5in; }
/* Nothing to click on paper. */
.appview .avsave { display: none; }
/* An exhibit is one page: the picture is fitted to what is left under its heading rather than
   running on and leaving a blank sheet behind it. */
.appview .sheet .pasted { break-inside: avoid; }
.appview .sheet .pasted img { max-height: 8.1in; max-width: 100%; width: auto; height: auto;
                              object-fit: contain; }
.appview .sheet .pasted embed { height: 8.1in; }
.appview { background: #fff; padding: 0; }
/* The page margin does the framing; the sheet keeps a little air above its first heading and
   below its last line so nothing sits on the trim. */
.appview .sheet { width: auto; max-width: none; margin: 0; box-shadow: none; padding: 0.16in 0 0.3in;
                  break-after: page; }
.appview .sheet:last-child { break-after: auto; }
"""


def to_pdf(view: dict, fonts: str = "") -> bytes:
    """The sheets as a PDF, drawn from the same HTML and stylesheet the portal shows."""
    from weasyprint import CSS, HTML             # imported here: only printing needs it
    page = (f'<!doctype html><html><head><meta charset="utf-8"><title>Driver application</title>'
            f'</head><body class="appview">{view["html"]}</body></html>')
    return HTML(string=page).write_pdf(stylesheets=[CSS(string=fonts + view["css"] + PRINT_CSS)])


def signature_css() -> str:
    """The signing faces, carried into the PDF as data so WeasyPrint needs nothing from the web."""
    out = []
    for key, file in (("modern", "ms-madi"), ("signature", "meddon"), ("quick", "kristi"),
                      ("hand", "zeyada"), ("cursive", "cedarville-cursive"),
                      ("fine", "herr-von-muellerhoff"), ("bold", "style-script")):
        path = Path(__file__).resolve().parent / "legal" / "forms" / f"{file}.ttf"
        if not path.exists():
            continue
        data = base64.b64encode(path.read_bytes()).decode()
        out.append(f"@font-face {{ font-family: 'TP {key}'; src: url(data:font/ttf;base64,{data}); }}")
        out.append(f".font-{key} {{ font-family: 'TP {key}'; }}")
    return "".join(out)


def signed_document(conn: Connection, accountid: str, driverid: str, doctype: str) -> dict | None:
    """One document as it was signed, on its own sheet: the wording that was shown, then the
    signature, the date and the audit stamp under it. Built from the record rather than from a copy,
    so what is read now is what was attested to then."""
    signings = signatures.signed(conn, accountid, driverid)
    sig = signings.get(doctype)
    if not sig:
        return None
    # A government form was signed ON THE FORM, so what exists is a file. Rebuilding our own
    # wording of it here would show the office a summary of the I-9 instead of the I-9, which is
    # not the thing anybody has to read before accepting it.
    onfile = row(conn, """
        SELECT documentid FROM signingrequests
        WHERE accountid = :a AND driverid = :d AND doctype = :t AND documentid IS NOT NULL
        ORDER BY createdon DESC LIMIT 1
    """, a=accountid, d=driverid, t=doctype)
    if onfile:
        company = row(conn, "SELECT name FROM accounts WHERE recordid = :a",
                      a=accountid)["name"]
        return {"doctype": doctype, "title": DOC_TITLES.get(doctype, doctype), "company": company,
                "signedon": sig["signedon"], "documentid": onfile["documentid"]}
    driver = row(conn, """
        SELECT recordid, firstname, lastname, dob FROM drivers
        WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=driverid, a=accountid)
    app_ = row(conn, """
        SELECT data FROM driverapplications WHERE driverid = :id AND accountid = :a
        ORDER BY startedon DESC LIMIT 1
    """, id=driverid, a=accountid)
    data = json.loads(app_["data"] or "{}") if app_ else {}
    company = row(conn, "SELECT name FROM accounts WHERE recordid = :a", a=accountid)["name"]
    licences = ((data.get("steps") or {}).get("2") or {}).get("licenses") or []
    cdl = next((l for l in licences if (l.get("classification") or "").upper() in ("A", "B", "C")), None) \
        or (licences[0] if licences else {})
    blanks = {"company": company, "fullname": _fullname_of(driver),
              "cdlstate": cdl.get("state", ""), "cdlnumber": cdl.get("number", ""),
              "dob": driver["dob"].strftime("%m/%d/%Y") if driver.get("dob") else ""}
    # A company policy is not reprinted from our wording - what was signed for is the file the
    # company had filed, so that file is shown, and the declaration and signature sit under it.
    if doctype == "APPLICATION":
        # The whole application: the form, every document signed with it, and every file attached.
        html = build(conn, accountid, company, driver, app_ or {"data": "{}"})
        return {"doctype": doctype, "title": DOC_TITLES.get(doctype, doctype), "company": company,
                "signedon": sig["signedon"], "html": html, "css": STYLE}
    if doctype in AFFIDAVIT:
        signed = f'Signed {_t(sig.get("signedon"))}' if sig.get('signedon') else 'Not signed'
        html = (f'<div class="sheet">'
                f'{_letterhead(company, DOC_TITLES.get(doctype, doctype), blanks["fullname"], signed)}'
                f'{_affidavit(conn, accountid, doctype, sig, company, blanks["fullname"])}</div>')
        code = POLICY_CODES.get(doctype)
        policy = _company_policy(conn, accountid, code) if code else None
        if policy:
            # The copy the company actually filed, on a page of its own. It was being pasted
            # in bare - outside any sheet, so it carried neither the letterhead nor the title,
            # and a policy read on its own said nothing about whose policy it was.
            head = _letterhead(company, AFFIDAVIT[doctype], blanks["fullname"], signed)
            try:
                shown = _embedded(storage.get(policy["storagekey"]),
                                  policy["mimetype"] or "application/pdf", AFFIDAVIT[doctype])
            except storage.Missing:
                shown = '<p class="none">The copy that was given is no longer stored.</p>'
            html = f'<div class="sheet">{head}{shown}</div>' + html
    else:
        # Already a sheet of its own - wrapping it in another was the paper-on-paper.
        html = _signed_sheet(conn, accountid, doctype, sig, blanks, data)
    return {"doctype": doctype, "title": DOC_TITLES.get(doctype, doctype), "company": company,
            "signedon": sig["signedon"], "html": html, "css": STYLE}


def signed_list(conn: Connection, accountid: str, driverid: str) -> list[dict]:
    """Everything this driver has signed, newest first."""
    out = []
    for doctype, sig in signatures.signed(conn, accountid, driverid).items():
        out.append({"doctype": doctype, "title": DOC_TITLES.get(doctype, doctype),
                    "signedon": sig["signedon"], "typedname": sig["typedname"], "ip": sig["ip"],
                    "recordid": sig["recordid"]})
    return sorted(out, key=lambda s: str(s["signedon"]), reverse=True)


def application_for(conn: Connection, accountid: str, driverid: str) -> dict | None:
    """The driver's application as printed sheets, or None if they never applied."""
    driver = row(conn, """
        SELECT recordid, firstname, lastname, dob, drivernumber, status FROM drivers
        WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=driverid, a=accountid)
    if not driver:
        return None
    app_ = row(conn, """
        SELECT recordid, status, step, data, submittedon, startedon FROM driverapplications
        WHERE driverid = :id AND accountid = :a ORDER BY startedon DESC LIMIT 1
    """, id=driverid, a=accountid)
    if not app_:
        return None
    company = row(conn, "SELECT name FROM accounts WHERE recordid = :a", a=accountid)["name"]
    return {"status": app_["status"], "submittedon": app_["submittedon"],
            "html": build(conn, accountid, company, driver, app_), "css": STYLE}
