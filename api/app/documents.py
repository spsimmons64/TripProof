###################################################################################################
# The text of everything a person signs.
#
# Each document lives as a file under legal/driver/. The server serves the text and hashes its own
# copy when a signature is recorded, so what is attested to is always what we published. The
# version travels with the signature: change the wording and the version changes with it, and old
# signatures still name the text they were made against.
#
# DRIVER_DOC_VERSION is bumped whenever any of these files is edited. The FCRA summary here is a
# plain-language recap; a live deployment should serve the official CFPB summary in its place.
###################################################################################################
from functools import lru_cache
from pathlib import Path

DRIVER_DOC_VERSION = "2026-09-25a"
_DIR = Path(__file__).resolve().parent / "legal" / "driver"

def fill(doc: dict, values: dict) -> dict:
    """Some documents name the company, the person signing, or what they hold a licence under. The
    blanks are filled here, on the server, so the text that is hashed is the text that was shown.

    What goes on the line is upper case, as it is everywhere else in the application, whatever case
    the record happens to be in."""
    text = doc["text"]
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value or "").upper())
    return {**doc, "text": text}


COMPANY_DIR = Path(__file__).resolve().parent / "legal" / "company"

# The policies a company holds and hands to its drivers. Held as templates rather than uploaded,
# so the Designated Employer Representative prints on them from the appointment on file and can
# never be the person who left last year - and so the wording can be corrected when the regulation
# changes, for every customer at once, instead of living as bespoke prose nobody can version.
COMPANY_POLICIES = {
    "DRUG_POLICY": "CDL / CMV Drug and Alcohol Testing Policy",
    "WORKPLACE_POLICY": "Company Drug and Alcohol Workplace Policy",
    "PHI_POLICY": "Driver PHI Confidentiality and Privacy Policy",
    "SSPP": "System Safety Program Plan",
    "SERVICE_AGENT_POLICY": "DOT Drug and Alcohol Testing Procedures and Service Agent "
                            "Oversight Policy",
    "RANDOM_TESTING_POLICY": "DOT Random Drug and Alcohol Testing Program",
    "BBP_EXPOSURE_DETERMINATION": "Bloodborne Pathogens Occupational Exposure Determination",
    # A published sheet like the rest of these, and edited like the rest of these. What makes it
    # different is only that each supervisor fills a copy of it in and signs it: the blank form
    # IS this policy, so there is one set of words rather than a policy and a form that drift.
    "SUPERVISOR_TRAINING_RECORD": "DOT Reasonable Suspicion Supervisor Training Record",
    "HIPAA_RISK_ANALYSIS_POLICY": "HIPAA Security Risk Analysis Policy",
}

# What a company chooses at section 10, in its own words. Three options rather than a text box:
# this is the one paragraph that is genuinely the company's own, and the rest is regulation.
DISCIPLINE = {
    "terminate": "A DOT drug or alcohol violation will result in termination of employment.",
    "discretion": "A DOT drug or alcohol violation may result in disciplinary action up to and "
                  "including termination. The Company may, in its discretion, permit an employee "
                  "to pursue the DOT return-to-duty process.",
}


def company_policy(code: str) -> dict:
    """One of the company's own policies, as published text waiting to be filled.

    Held as HTML because a company edits it in a rich text editor, and because the same markup then
    goes to the screen, to print and into the copy a driver receives without a second format in the
    middle. The Markdown beside it is the source these were written from, kept so the published
    wording stays readable in a diff."""
    if code not in COMPANY_POLICIES:
        raise KeyError(code)
    path = COMPANY_DIR / f"{code}.html"
    return {"code": code, "title": COMPANY_POLICIES[code], "format": "html",
            "version": DRIVER_DOC_VERSION, "text": path.read_text(encoding="utf-8").strip()}


def fill_exact(text: str, values: dict) -> str:
    """Fill blanks without shouting.

    `fill` upper-cases what it puts on a line, which is right for a name written onto a form and
    wrong for twenty pages of policy - a telephone number and an email address in capitals read as
    a mistake. Used where the document is prose rather than a form."""
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value if value is not None else ""))
    return text


TITLES = {
    "I9": "Form I-9, Employment Eligibility Verification",
    "W4": "Form W-4, Employee's Withholding Certificate",
    "FCRA_SUMMARY": "A Summary of Your Rights Under the Fair Credit Reporting Act",
    "FCRA_AUTH": "Disclosure and authorization for employment background check",
    "WORKPLACE_POLICY": "Workplace policy acknowledgement",
    "DRUG_POLICY": "Drug and alcohol policy acknowledgement",
    "PHI_ACK": "PHI confidentiality and privacy acknowledgment",
    "CLEARINGHOUSE_CONSENT": "FMCSA Clearinghouse query consent",
    "SAFETY_PERFORMANCE_CONSENT": "Consent to release safety performance history",
    "APPLICATION": "Driver application certification",
}


@lru_cache(maxsize=None)
def driver_document(doctype: str) -> dict:
    """The text to sign. A document may be held as Markdown or, where it reproduces a published
    document with a layout of its own, as HTML - the official FCRA summary has a table of agencies
    in it, which Markdown of ours could not carry. Raises KeyError for anything not in TITLES, so a
    caller cannot read arbitrary files through this.

    Either way it is our own copy that is read and hashed, so what is attested to is what we
    published."""
    if doctype not in TITLES:
        raise KeyError(doctype)
    for suffix, fmt in ((".html", "html"), (".md", "markdown")):
        path = _DIR / f"{doctype}{suffix}"
        if path.exists():
            return {"doctype": doctype, "title": TITLES[doctype], "version": DRIVER_DOC_VERSION,
                    "format": fmt, "text": path.read_text(encoding="utf-8").strip()}
    raise KeyError(doctype)
