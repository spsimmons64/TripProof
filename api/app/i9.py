###################################################################################################
# Form I-9, filled in and flattened.
#
# The blank is the official USCIS form, kept in legal/forms/i-9.pdf and never edited. We read the
# position of each Section 1 field from the form's own widgets, draw the answers into those boxes,
# and then drop the form fields entirely. What comes out is a flat page: nothing on it can be typed
# over, which is what 8 CFR 274a.2(e)(1)(ii) asks of an electronically stored I-9.
#
# Page 1 is what the applicant is shown - Section 2 below it belongs to the employer, and the
# supplements are not theirs to fill.
#
# The signature is drawn in the same face the driver adopted for the rest of the application, with
# the date beside it, and is affixed once, at the moment of signing: the signed PDF is stored and
# served from then on, never rebuilt.
###################################################################################################
import io
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from app import pdfform

_DIR = Path(__file__).resolve().parent / "legal" / "forms"
FORM = _DIR / "i-9.pdf"
# The edition of the blank we ship, from the form's own footer. It travels with every signature.
I9_EDITION = "I-9 edition 01/20/25, expires 05/31/2027"

PAGE = pdfform.LETTER
from app.signatures import SIGNATURE_FONTS      # one map, read by both forms

# The four boxes of the Section 1 attestation, in the order the form numbers them.
STATUS_BOXES = {"citizen": "CB_1", "national": "CB_2", "permanent": "CB_3", "authorized": "CB_4"}

# The one Section 1 field the blank rules into separate character cells (/MaxLen 9, comb flag set)
# rather than leaving as a line.
SSN_CELLS = "US Social Security Number"

# Section 2, the employer's certification. The form's own field names, which read as the sentences
# they sit under rather than as anything systematic.
SECTION2 = {
    "who": "Last Name First Name and Title of Employer or Authorized Representative",
    "signature": "Signature of Employer or AR",
    "signedon": "S2 Todays Date mmddyyyy",
    "firstday": "FirstDayEmployed mmddyyyy",
    "orgname": "Employers Business or Org Name",
    "orgaddress": "Employers Business or Org Address",
}


# Every date box on this form is labelled "(mm/dd/yyyy)", Section 1 and Section 2 alike. The
# field NAMES say mmddyyyy, which is what the 2019 edition's character-comb boxes wanted; the
# edition we ship is one box per date and prints the separators.
_mmddyyyy = pdfform.mdy


def section1(app_: dict, answers: dict, ssn: str | None) -> dict:
    """Everything the employee's half of the form asks for, as the field names the blank uses.
    Written in upper case, as the rest of the application is."""
    status = (answers.get("citizenship") or "").strip()
    values = {
        "Last Name (Family Name)": (app_.get("lastname") or "").upper(),
        "First Name Given Name": (app_.get("firstname") or "").upper(),
        "Employee Middle Initial (if any)": (answers.get("middleinitial") or "")[:1],
        "Employee Other Last Names Used (if any)": answers.get("othernames") or "",
        "Address Street Number and Name": answers.get("address1") or "",
        "Apt Number (if any)": answers.get("apt") or "",
        "City or Town": answers.get("city") or "",
        "State": answers.get("state") or "",
        "ZIP Code": answers.get("zip") or "",
        "Date of Birth mmddyyyy": _mmddyyyy(app_.get("dob")),
        "US Social Security Number": "".join(c for c in (ssn or "") if c.isdigit()),
        "Employees E-mail Address": answers.get("email") or "",
        "Telephone Number": answers.get("phone") or "",
    }
    if status == "permanent":
        values["3 A lawful permanent resident Enter USCIS or ANumber"] = answers.get("anumber") or ""
    if status == "authorized":
        values["Exp Date mmddyyyy"] = _mmddyyyy(answers.get("workuntil"))
        values["USCIS ANumber"] = answers.get("anumber") or ""
        values["Form I94 Admission Number"] = answers.get("i94") or ""
        values["Foreign Passport Number and Country of IssuanceRow1"] = answers.get("passport") or ""
    return values


def _blank_boxes() -> dict:
    """Where every field sits on the pristine blank.

    Section 2 is written onto a page that has already been flattened once, and a flat page has no
    widgets left to ask. The geometry is read from the blank we ship instead, which is the same
    page the driver's copy was drawn on."""
    return pdfform.boxes(PdfReader(str(FORM)).pages[0])


def build(app_: dict, answers: dict, ssn: str | None, signature: str | None = None,
          fontkey: str = "modern", signedon: date | None = None, stamp: dict | None = None) -> bytes:
    """Page 1 of the official form with Section 1 written into it, flattened."""
    pages = list(PdfReader(str(FORM)).pages)
    pen = pdfform.Pen(pdfform.boxes(pages[0]), fontdir=_DIR)

    for field, value in section1(app_, answers, ssn).items():
        # The Social Security number is the one field on this form that is a character grid
        # rather than a line - nine ruled cells, one digit each.
        if field == SSN_CELLS:
            pen.comb(field, str(value), cells=9)
        else:
            pen.write(field, str(value).upper())

    pen.tick(STATUS_BOXES.get((answers.get("citizenship") or "").strip()) or "")

    if signature:
        face = pen.face(SIGNATURE_FONTS.get(fontkey, SIGNATURE_FONTS["modern"]))
        pen.write("Signature of Employee", signature, size=16, font=face)
        pen.write("Today's Date mmddyyy", _mmddyyyy(signedon or date.today()))
        pen.stamp("Signature of Employee", stamp)

    return pen.onto(pages)


def certify(filed: bytes, employer: dict, signature: str | None = None, fontkey: str = "modern",
            signedon: date | None = None, stamp: dict | None = None) -> bytes:
    """Section 2 written onto the copy the employee already signed.

    The employee's half is not re-rendered. The page handed in here is the flat one that was
    stored at the moment they signed it, and the employer's block is drawn onto that - so the hand
    on the Section 1 line, and the stamp behind it, are the same marks that were made then. An I-9
    rebuilt from scratch at certification time would print today's data over a signature given on
    an earlier day, which is the one thing the flattening is there to prevent.

    `employer` carries what 8 CFR 274a.2(b)(1)(ii) asks the employer to state: who they are, the
    business they act for, where it is, and the employee's first day of work. None of it is typed
    by the person certifying - it is the company on file, the hire date on the driver's record,
    and the account of whoever is signing.

    WHAT THIS DOES NOT FILL. The List A / List B / List C table above the certification says which
    identity and work-authorisation documents were physically examined. Nothing on file can answer
    that: only the person who looked at them knows what they were shown, and an employer that
    guesses at a document title has attested to examining a document it never saw.
    """
    pages = list(PdfReader(io.BytesIO(filed)).pages)
    pen = pdfform.Pen(_blank_boxes(), fontdir=_DIR)

    pen.write(SECTION2["who"], (employer.get("who") or "").upper())
    pen.write(SECTION2["orgname"], (employer.get("orgname") or "").upper())
    pen.write(SECTION2["orgaddress"], (employer.get("orgaddress") or "").upper())
    pen.write(SECTION2["firstday"], _mmddyyyy(employer.get("firstday")))

    if signature:
        face = pen.face(SIGNATURE_FONTS.get(fontkey, SIGNATURE_FONTS["modern"]))
        # The employer's hand gets the same block the employee's does: the signature, and beside it
        # which signature on file it was, when it was made and from where. A signature with no
        # stamp behind it is a picture of a name - the stamp is the part that makes it evidence,
        # and it belongs against the signature it describes rather than in a note somewhere else
        # on the page.
        #
        # This box is 191pt wide against the employee's 323, so the hand is held to the left of it
        # and the stamp is given the measured remainder.
        pen.write(SECTION2["signature"], signature, size=14, font=face, maxwidth=92)
        pen.write(SECTION2["signedon"], _mmddyyyy(signedon or date.today()))
        pen.stamp(SECTION2["signature"], stamp, reserve=97)

    return pen.onto(pages)
