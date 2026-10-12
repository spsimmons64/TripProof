###################################################################################################
# Reading a driver's licence from the barcode on its back.
#
# Every US and Canadian licence carries a PDF417 barcode holding an AAMVA record: the licence
# number, the jurisdiction, the class, the endorsements and restrictions, the issue and expiry
# dates, the name and the date of birth. That is the whole of what the application asks for, so an
# applicant who can photograph the back of their licence should not have to type any of it.
#
# This is best effort and nothing depends on it. A barcode that will not decode - and a photograph
# taken at an angle, or with a flash across it, often will not - simply returns nothing, and the
# applicant types what they always typed.
#
# Nothing here is trusted: what comes back is shown to the applicant to check and confirm before it
# joins their application. A misread licence number is worse than a typed one.
###################################################################################################
import io
import logging
import re
from datetime import date

from PIL import Image, ImageOps

log = logging.getLogger("tripproof.license")

# The issuer identification number in the barcode header names the jurisdiction. Only the ones a
# driver here plausibly holds are listed; an unknown issuer just leaves the state to the applicant.
ISSUERS = {
    "636000": "VA", "636001": "NY", "636002": "MA", "636003": "MD", "636004": "NC", "636005": "SC",
    "636006": "MO", "636007": "NE", "636008": "WA", "636009": "OR", "636010": "CA", "636011": "TN",
    "636012": "OK", "636013": "MI", "636014": "CA", "636015": "FL", "636016": "PR", "636017": "AL",
    "636018": "AK", "636019": "WY", "636020": "TX", "636021": "ID", "636022": "UT", "636023": "IA",
    "636024": "MN", "636025": "MT", "636026": "NV", "636027": "NM", "636028": "ND", "636029": "OH",
    "636030": "PA", "636031": "RI", "636032": "SD", "636033": "TX", "636034": "VT", "636035": "WV",
    "636036": "WI", "636037": "AR", "636038": "CO", "636039": "CT", "636040": "DE", "636041": "DC",
    "636042": "GA", "636043": "HI", "636044": "IL", "636045": "IN", "636046": "KS", "636047": "KY",
    "636048": "LA", "636049": "ME", "636050": "MS", "636051": "NH", "636052": "NJ", "636053": "AZ",
    "636054": "GU", "636055": "VI", "636058": "AS", "636059": "MP",
}

# What the class on the card means in the wizard's own list. Anything else is offered as Other, so
# the applicant sees it was read and can correct it.
CLASSES = {"A", "B", "C", "D", "E", "M"}
ENDORSEMENTS = {"H", "T", "N", "S", "P", "X"}


def _text(blob: bytes) -> str | None:
    """The barcode's contents, or None. Tries the frame as it came, then turned about - a licence
    photographed on a desk is as often upside down as not - then the lower band on its own, which is
    where the barcode sits on the back of the card."""
    try:
        import zxingcpp
    except ImportError:                                   # the reader is optional; typing still works
        log.info("zxing-cpp is not installed, so licences cannot be read")
        return None
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(blob))).convert("L")
    except Exception:
        return None
    w, h = image.size
    attempts = [image, image.rotate(180)]
    if h > 400:
        band = image.crop((0, int(h * 0.45), w, h))
        attempts += [band, band.rotate(180)]
    for attempt in attempts:
        try:
            hits = zxingcpp.read_barcodes(attempt, formats=zxingcpp.BarcodeFormat.PDF417,
                                          try_rotate=True, try_downscale=True, try_invert=True)
        except Exception:
            return None
        if hits:
            # The reader's `text` is for people to look at: it writes control characters as <LF> and
            # <CR>, which are exactly the separators this record is made of. The bytes are the record.
            raw = getattr(hits[0], "bytes", None)
            if raw:
                return bytes(raw).decode("utf-8", "replace")
            if hits[0].text:
                return hits[0].text
    return None


def _date(value: str | None) -> str | None:
    """AAMVA dates are eight digits. A US card writes MMDDCCYY and a Canadian one CCYYMMDD, so the
    first four digits decide: a plausible year means the year came first."""
    if not value or not value.isdigit() or len(value) != 8:
        return None
    head = int(value[:4])
    if 1900 <= head <= 2100:
        y, m, d = value[0:4], value[4:6], value[6:8]
    else:
        m, d, y = value[0:2], value[2:4], value[4:8]
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return None


def _fields(text: str) -> dict[str, str]:
    """The three-letter elements of the record. Each sits at the start of a line, and the value runs
    to the end of it - except the first, which follows the subfile marker on the header line with
    nothing between them."""
    out: dict[str, str] = {}
    # The record proper starts at the subfile marker, which is the "DL" immediately in front of the
    # first element - everything before it is the header and its offsets.
    start = re.search(r"DL(?=D[A-Z]{2})", text)
    for line in re.split(r"[\r\n]+", text[start.end():] if start else text):
        line = line.strip()
        if len(line) > 3 and line[:3].isalpha() and line[:3].isupper():
            out.setdefault(line[:3], line[3:].strip())
    return out


def _codes(value: str | None, allowed: set[str]) -> list[str]:
    """'NONE' and 'N/A' mean none. Anything else is read letter by letter and kept if we know it."""
    if not value or value.strip().upper() in ("NONE", "N/A", "NA", "-"):
        return []
    return sorted({c for c in value.upper() if c in allowed})


def read(blob: bytes) -> dict | None:
    """What the barcode says, in the shape the licence dialog uses. None when nothing could be read."""
    text = _text(blob)
    if not text:
        return None
    f = _fields(text)
    number = f.get("DAQ")
    if not number:
        return None

    state = (f.get("DAJ") or "").strip().upper()[:2]
    if len(state) != 2:
        issuer = re.search(r"\d{6}", text[:40])
        state = ISSUERS.get(issuer.group(0), "") if issuer else ""

    klass = (f.get("DCA") or "").strip().upper()
    # A class arrives as a letter, sometimes with the jurisdiction's own suffix behind it.
    letter = next((c for c in klass if c in CLASSES), "")

    name = " ".join(p for p in ((f.get("DAC") or f.get("DCT") or "").strip(),
                                (f.get("DAD") or "").strip(),
                                (f.get("DCS") or "").strip()) if p)
    out = {
        "number": number.strip().upper(),
        "state": state,
        "classification": letter or ("O" if klass else ""),
        "endorsements": _codes(f.get("DCD"), ENDORSEMENTS),
        "restrictions": (f.get("DCB") or "").strip().upper(),
        "issued": _date(f.get("DBD")),
        "expires": _date(f.get("DBA")),
        "dob": _date(f.get("DBB")),
        "name": name.upper(),
        "rawclass": klass,
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])} | {"endorsements": out["endorsements"]}
