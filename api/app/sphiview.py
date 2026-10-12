###################################################################################################
# The completed SPHI, as the document it has to be - 49 CFR 391.23, retained under 391.53.
#
# What an auditor asks for is not a row in a table. It is the form, filled in, signed by the person
# at the previous employer who answered it, on the carrier's letterhead with the date on it. So the
# answers are rendered back into the form they were asked in and kept as a PDF, drawn from the same
# sheets, stylesheet and signature faces the application and every signed consent already use.
#
# THE EMPLOYER'S SIGNATURE
#
# They sign it the way a driver or an office user signs anything here: they type their name and it
# is drawn in a hand. What is different is that nobody proves who they are first - there is nothing
# to prove against. A previous employer has no record in this system, no date of birth we hold and
# no Social Security number we could ever ask for.
#
# So the typed name is used to draw the signature and is not kept as a signature of record: there is
# no `signatures` row, nothing adopted, nothing carried forward to a later document. It signs this
# one page and goes no further. What is kept is the page - which is exactly what the paper form
# produces when somebody signs it and faxes it back.
###################################################################################################
from datetime import date

from sqlalchemy.engine import Connection

from app import applicationview as view
from app import storage
from app.db import row, run, utcnow

# How each answer reads once it is on paper. The vocabularies are small and the words are the
# form's own, so a stored "norecords" never reaches a page as "norecords".
VERIFIED = {"yes": "Yes", "no": "No", "unable": "Unable to verify"}
ACCIDENT = {"no": "No", "yes": "Yes", "norecords": "No records available"}
YESNO = {"yes": "Yes", "no": "No", "na": "N/A - no records"}
FOURWAY = {"yes": "Yes", "no": "No", "unknown": "Unknown", "na": "Not applicable"}

DA_QUESTIONS = (
    ("alcohol04", "Alcohol test result of 0.04 or greater?"),
    ("positivetest", "Verified positive controlled-substances test?"),
    ("refusedtest", "Refusal to submit to a required DOT drug/alcohol test?"),
    ("otherviolation", "Other applicable DOT drug/alcohol prohibition violation?"),
)
SAP_QUESTIONS = (
    ("sapevaluated", "SAP evaluation completed?"),
    ("saptreatment", "SAP-prescribed education/treatment completed?"),
    ("rtdtest", "Required return-to-duty test completed with acceptable result?"),
    ("followupplan", "Driver subject to a follow-up testing plan?"),
)


def _day(value):
    """A date where the form asks for a date. A timestamp with an hour and a timezone in it is more
    than the form records and wraps the blank it sits on."""
    return value.date() if hasattr(value, "date") else value


def _said(vocabulary: dict, value) -> str:
    """An answer in the form's words, or a blank where it was not asked."""
    return vocabulary.get((value or "").lower(), "-") if value else "-"


def _answers(title: str, questions, inq: dict, vocabulary: dict) -> str:
    rows_ = [[label, _said(vocabulary, inq.get(key))] for key, label in questions]
    return view._section(title, view._rows([("Question", 74), ("Answer", 26)], rows_, least=0))


def build(inq: dict, driver: dict, account: dict) -> str:
    """The whole form as one sheet, in the order the paper form asks it."""
    name = f'{driver["firstname"]} {driver["lastname"]}'.strip().title()
    head = view._letterhead(account["name"], "Safety Performance History Investigation",
                            name, f'Answered {view._t(_day(inq["respondedon"]))}')

    # Every blank takes half the width, so a pair fills the line and nothing is left hanging in a
    # third of a row with a date wrapping inside it.
    applicant = view._section("Driver / Applicant", (
        '<div class="fields">'
        + view._blank("Driver name", name, 6)
        + view._blank("Date of birth", driver.get("dob"), 6)
        + view._blank("Driver license no.", driver.get("licensenumber"), 6)
        + view._blank("Issuing state", driver.get("licensestate"), 6)
        + "</div>"))

    requestor = view._section("Prospective Employer / Requestor", (
        '<div class="fields">'
        + view._blank("Company", account["name"], 6)
        + view._blank("Phone", account.get("phone"), 6)
        + view._blank("Address", account.get("address1"), 6)
        + view._blank("Email", account.get("email"), 6)
        + view._blank("City / State / ZIP", ", ".join(
            [x for x in (account.get("city"), account.get("state"), account.get("zip")) if x]), 6)
        # The day it was sent. The hour it was sent is not part of the record this form keeps, and
        # printing one made the blank wrap onto two lines.
        + view._blank("Date request sent", _day(inq.get("createdon")), 6)
        + "</div>"))

    previous = view._section("Previous DOT-Regulated Employer", (
        '<div class="fields">'
        + view._blank("Company", inq["employer"], 6)
        + view._blank("Contact", inq.get("contactname"), 6)
        + view._blank("Address", inq.get("address1"), 6)
        + view._blank("Phone", inq.get("phone"), 6)
        + view._blank("City / State / ZIP", ", ".join(
            [x for x in (inq.get("city"), inq.get("state"), inq.get("zip")) if x]), 6)
        + view._blank("Email", inq.get("email"), 6)
        + "</div>"
        + view._box("Employment verified?", inq.get("employmentverified"),
                    options=("yes", "no", "unable"))
        + '<div class="fields">'
        + view._blank("From", inq.get("confirmedfrom") or inq.get("employedfrom"), 3)
        + view._blank("To", inq.get("confirmedthrough") or inq.get("employedthrough"), 3)
        + view._blank("Position", inq.get("position"), 3)
        + view._blank("DOT mode", inq.get("dotmode"), 3)
        + "</div>"
        + view._box("Operated a CMV?", inq.get("operatedcmv"),
                    options=("yes", "no", "unknown", "na"))))

    entries = inq.get("accidents")
    entries = entries if isinstance(entries, list) else []
    accidents = view._section("Accident History - Preceding 3 Years", (
        view._box("Was the driver involved in any accidents required to be maintained under "
                  "49 CFR 390.15?", inq.get("accidentanswer"), options=("no", "yes", "norecords"))
        + view._rows([("Date", 16), ("Location", 34), ("Fatalities", 12), ("Injuries", 12),
                      ("Hazmat", 10), ("Notes", 16)],
                     [[a.get("date"), a.get("location"), a.get("fatalities"), a.get("injuries"),
                       "Yes" if a.get("hazmat") else "No", a.get("note")] for a in entries],
                     least=1 if entries else 0)))

    drugalcohol = _answers("Drug And Alcohol History", DA_QUESTIONS, inq, YESNO)
    sap = _answers("SAP / Return-To-Duty Information", SAP_QUESTIONS, inq, FOURWAY)
    # Whatever the questions had no box for, in a section of its own rather than tucked under the
    # certification - it is part of what is being certified, not a remark about the signing.
    anything = view._section("Anything Else", (
        '<div class="fields">' + view._note("", inq.get("responsenote"), 12) + "</div>"))

    # The certification, with the name drawn as a signature. Nothing was proved and nothing is
    # claimed to have been: it is a name somebody typed, exactly as a name on a faxed form is.
    typed = inq.get("certsignature") or inq.get("respondedby") or ""
    drawn = view.signature_image(typed, inq.get("certfontkey") or "modern")
    # What proves the signing, on one line under it. There is no identity check behind it and the
    # stamp does not pretend otherwise: it says who typed the name, from where, and when.
    stamp = " · ".join(filter(None, [
        "Signed electronically", typed, view._t(inq.get("respondedon")),
        f'IP {inq.get("respondedip") or "not recorded"}',
    ]))
    certification = (
        '<div class="section certify"><div class="bar">Previous Employer Certification</div>'
        '<p>I certify that the information provided is based on records available to this '
        'company.</p>'
        '<div class="fields">'
        + view._blank("Name", inq.get("respondedby"), 6)
        + view._blank("Title", inq.get("certtitle"), 6)
        + view._blank("Company", inq.get("certcompany"), 6)
        + view._blank("Phone", inq.get("certphone"), 6)
        + view._blank("Email", inq.get("certemail"), 6)
        + view._blank("Date", _day(inq.get("respondedon")), 6)
        + "</div>"
        # The same signature line every other signed sheet here uses, so a page pulled from this
        # file reads the same as one pulled from the application.
        + '<div class="avrow"><div class="avline">'
        + f'<span class="avwritten"><img class="avsig" alt="Signature" src="{drawn}"></span>'
        + '<span class="avcap">Signature of previous employer</span></div>'
        + f'<div class="avline avshort"><span class="avval">{view._t(_day(inq["respondedon"]))}</span>'
        + '<span class="avcap">Date signed</span></div></div>'
        + f'<p class="avstamp">{view.escape(stamp)}</p>'
        + "</div>")

    return (f'<div class="sheet">{head}{applicant}{requestor}{previous}{accidents}'
            f'{drugalcohol}{sap}{anything}{certification}</div>')


def keep(conn: Connection, inquiryid: str) -> str | None:
    """Render the answered inquiry and file it as the document of record.

    Called the moment the employer submits, so what is kept is what they saw and signed - not a
    page rebuilt later from columns that may since have been edited."""
    inq = row(conn, "SELECT * FROM employerinquiries WHERE recordid = :i", i=inquiryid)
    if not inq or not inq.get("respondedon"):
        return None
    driver = row(conn, """
        SELECT firstname, lastname, dob, licensenumber, licensestate
        FROM drivers WHERE recordid = :d
    """, d=inq["driverid"])
    account = row(conn, """
        SELECT name, address1, city, state, zip, phone, email FROM accounts WHERE recordid = :a
    """, a=inq["accountid"])
    if not driver or not account:
        return None
    html = build(dict(inq), dict(driver), dict(account))
    pdf = view.to_pdf({"html": html, "css": view.STYLE}, view.signature_css())
    documentid = storage.keep(conn, inq["accountid"], "documents", pdf,
                              f'SPHI - {inq["employer"]}.pdf', "application/pdf", None, origin=storage.THIRDPARTY)
    run(conn, "UPDATE employerinquiries SET documentid = :doc WHERE recordid = :i",
        doc=documentid, i=inquiryid)
    return documentid


__all__ = ["build", "keep"]
