###################################################################################################
# Form W-4, filled in and flattened.
#
# The same treatment the I-9 gets, for the same reason: the blank is the IRS's own form, kept in
# legal/forms/fw4.pdf and never edited. The positions of the Step 1 to Step 5 boxes are read from
# the form's own widgets, the answers are drawn into them, and the form fields are then dropped.
# What a driver signs and what is stored afterwards is a flat page - nothing on it can be typed
# over later, and nobody can argue the figures changed after the signature went on.
#
# Page 1 only. Pages 2 to 4 are the IRS's instructions and worksheets: the Multiple Jobs Worksheet
# and the Deductions Worksheet are the employee's own working, not part of what they file, and the
# employer never sees them. Only page 1 is given to the employer, and only page 1 is signed.
#
# WHAT IS NOT ASKED, and why. Steps 2, 3 and 4 are optional and personal - a second job, a spouse's
# income, dependants, other income somebody does not want their employer to know the detail of. The
# form is deliberately built so that a driver who fills in nothing but their name, address, Social
# Security number, filing status and signature has filed a complete and valid W-4. So those steps
# are offered and never required, and nothing here guesses at a number on somebody's behalf: an
# employer that invents a withholding allowance has made a decision that is not theirs to make.
###################################################################################################
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from app import pdfform

_DIR = Path(__file__).resolve().parent / "legal" / "forms"
FORM = _DIR / "fw4.pdf"
# The edition of the blank we ship, from the form's own footer. It travels with every signature, so
# a form signed under one year's edition can always be told from one signed under another.
W4_EDITION = "W-4 (2026)"

PAGE = pdfform.LETTER
from app.signatures import SIGNATURE_FONTS      # one map, read by both forms

# The form's own field names, which are positional rather than descriptive - f1_01 and the rest -
# so what each one is gets said here once.
STEP1 = {
    "f1_01[0]": "firstname",      # first name and middle initial
    "f1_02[0]": "lastname",
    "f1_03[0]": "address",
    "f1_04[0]": "citystatezip",
    "f1_05[0]": "ssn",
}
# Step 1(c). One of three, and the labels are the IRS's own wording rather than a paraphrase.
FILING = {
    "single": ("c1_1[0]", "Single or Married filing separately"),
    "joint": ("c1_1[1]", "Married filing jointly or Qualifying surviving spouse"),
    "head": ("c1_1[2]", "Head of household"),
}
STEP2C = "c1_2[0]"            # the two-jobs box
STEP3_CHILDREN = "f1_06[0]"   # qualifying children under 17, multiplied by $2,000
STEP3_OTHERS = "f1_07[0]"     # other dependants, multiplied by $500
STEP3_TOTAL = "f1_08[0]"
STEP4A = "f1_09[0]"           # other income
STEP4B = "f1_10[0]"           # deductions
STEP4C = "f1_11[0]"           # extra withholding per pay period

# The bottom strip, and the one place the form's own numbering misleads. The three widgets along
# the foot of the page are NOT the signature and its date - they are the "Employers Only" row:
#
#   f1_12   Employer's name and address
#   f1_13   First date of employment
#   f1_14   Employer identification number (EIN)
#
# The Step 5 signature line above them has no widget at all. The IRS rules it and leaves it, so
# there is nothing to look up by name and the signature was going into the employer's address box
# instead - the driver's hand printed under a heading that says "Employers Only".
EMPLOYER_ADDRESS = "f1_12[0]"
FIRST_DAY = "f1_13[0]"
EIN = "f1_14[0]"

# Step 5, measured off the form itself rather than named: the rule the signature sits on runs from
# the end of the "Sign Here" column to the Date column, and the labels under both baselines are at
# y=81.7. A box is built on those coordinates so the signature is written the same way every other
# entry on the form is.
SIGNATURE = "step5 signature"
SIGNED_ON = "step5 date"
#
# The signature box sits higher than the date box on purpose. A script face at 16pt has long
# descenders, and centred on the date's band it writes straight through the rule and the
# "Employee's signature" caption printed under it. It is given the clear air up to the Step 5
# sentence instead, so the hand sits ON the line rather than across the words.
STEP5_BOXES = {
    SIGNATURE: (102.8, 90.0, 452.0, 110.0),
    SIGNED_ON: (462.8, 89.0, 576.0, 104.0),
}


_mdY = pdfform.mdy


def step1(driver: dict, answers: dict, ssn: str | None) -> dict:
    """What the employee fills in, by the form's own field names.

    Only Step 1 is required of anybody. Everything after it is written only where the driver
    actually answered, because a blank box on a W-4 is a valid answer and a zero is not the same
    thing as one.
    """
    first = (driver.get("firstname") or "").strip()
    initial = (answers.get("middleinitial") or "").strip()[:1]
    town = ", ".join(x for x in [(answers.get("city") or "").strip(),
                                 " ".join(x for x in [(answers.get("state") or "").strip(),
                                                      (answers.get("zip") or "").strip()] if x)]
                     if x)
    values = {
        "f1_01[0]": f"{first} {initial}".strip(),
        "f1_02[0]": (driver.get("lastname") or "").strip(),
        "f1_03[0]": (answers.get("address1") or "").strip(),
        "f1_04[0]": town,
        "f1_05[0]": "".join(c for c in (ssn or "") if c.isdigit()),
    }
    for field, key in ((STEP3_CHILDREN, "children"), (STEP3_OTHERS, "dependants"),
                       (STEP3_TOTAL, "dependanttotal"), (STEP4A, "otherincome"),
                       (STEP4B, "deductions"), (STEP4C, "extrawithholding")):
        said = answers.get(key)
        if said not in (None, ""):
            values[field] = str(said)
    return values


def build(driver: dict, answers: dict, ssn: str | None, signature: str | None = None,
          fontkey: str = "modern", signedon: date | None = None, stamp: dict | None = None,
          employer: dict | None = None) -> bytes:
    """Page 1 of the official form with the employee's half written into it, flattened.

    `employer` is the Employers Only row at the foot of the page - the company's name and address,
    the employee's first day, and the EIN. It is the employer's own record of the certificate and
    nobody signs it, so unlike the I-9's Section 2 it is simply filled from what is on file at the
    moment the form is built.
    """
    pages = list(PdfReader(str(FORM)).pages)
    # The W-4's tick boxes are smaller than the I-9's, so the mark is drawn a shade smaller and a
    # shade lower to sit inside them.
    pen = pdfform.Pen({**pdfform.boxes(pages[0]), **STEP5_BOXES}, fontdir=_DIR)
    tick = lambda field: pen.tick(field, size=10, dx=3, dy=1)   # noqa: E731

    for field, value in step1(driver, answers, ssn).items():
        pen.write(field, str(value).upper())

    chosen = FILING.get((answers.get("filing") or "").strip())
    if chosen:
        tick(chosen[0])
    if answers.get("twojobs"):
        tick(STEP2C)

    if employer:
        # "Employer's name and address" is one box 30pt tall - two lines of room, which is what
        # the label is asking for. Squeezing the name and the address onto one line shrank both
        # to fit and read as a footnote; they get a line each at full size.
        pen.note(EMPLOYER_ADDRESS,
                 [x.upper() for x in (employer.get("orgname"), employer.get("orgaddress")) if x],
                 size=9.5, leading=1.5)
        pen.write(FIRST_DAY, _mdY(employer.get("firstday")))
        pen.write(EIN, (employer.get("ein") or "").upper())

    if signature:
        face = pen.face(SIGNATURE_FONTS.get(fontkey, SIGNATURE_FONTS["modern"]))
        # Held to the left half of the rule so a long name cannot run under the stamp beside it.
        pen.write(SIGNATURE, signature, size=16, font=face, maxwidth=190)
        pen.write(SIGNED_ON, _mdY(signedon or date.today()))
        pen.stamp(SIGNATURE, stamp, reserve=195)

    return pen.onto(pages)
