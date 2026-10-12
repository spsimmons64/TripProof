###################################################################################################
# The pre-employment drug and alcohol questionnaire, as the document it has to be - 49 CFR 40.25(j).
#
# The ANSWER is a fact and lives on the driver's own application, where the rule reads it. That is
# right and it is not enough: what an auditor asks for is the form, with the question on it in the
# words it was asked in, the answer the applicant gave, and their signature under it. A row in a
# table is not that, and neither is a sentence in a screen.
#
# So the answer is rendered back into the form it was asked in and kept as a PDF, from the same
# sheets, stylesheet and signature faces the application and every signed consent already use. The
# fact is still held in one place; this is a view of it, drawn at the moment it was signed.
#
# It is drawn when the driver sends it, not later on demand, for the same reason the SPHI reply is:
# what is kept must be what they saw and signed, not a page rebuilt from columns somebody may have
# edited since.
###################################################################################################
from sqlalchemy.engine import Connection

from app import applicationview as view
from app import images
from app import storage
from app.db import row, run

# The question, in the words 49 CFR 40.25(j) asks it in. It is on the page because a form with the
# answer but not the question is not a record of anything.
QUESTION = (
    "During the previous two years, have you tested positive, or refused to test, on any "
    "pre-employment drug or alcohol test administered by an employer to which you applied for, but "
    "did not obtain, safety-sensitive transportation work covered by DOT drug and alcohol testing "
    "rules?"
)
CERTIFY = ("I certify that the answer above is true and complete to the best of my knowledge.")

KIND = {"drug": "Drug", "alcohol": "Alcohol", "refusal": "Refusal to test"}
RTD = {"yes": "Yes", "inprogress": "In progress", "no": "No"}


def build(answer: dict, driver: dict, account: dict, signature: dict | None) -> str:
    """The whole questionnaire as one sheet, in the order it was asked."""
    name = f'{driver["firstname"]} {driver["lastname"]}'.strip().title()
    said = (answer.get("priorviolation") or "").lower()
    signedon = (signature or {}).get("signedon")
    head = view._letterhead(account["name"], "Pre-Employment Drug And Alcohol Questionnaire",
                            name, f'Answered {view._t(signedon)}' if signedon else "")

    applicant = view._section("Applicant", (
        '<div class="fields">'
        + view._blank("Driver name", name, 6)
        + view._blank("Date of birth", driver.get("dob"), 6)
        + view._blank("Driver license no.", driver.get("licensenumber"), 6)
        + view._blank("Issuing state", driver.get("licensestate"), 6)
        + "</div>"))

    asked = view._section("49 CFR 40.25(j)", (
        f'<p>{view.escape(QUESTION)}</p>'
        + view._box("Answer", said, options=("no", "yes"))))

    # Only where there is something to say. A form with four empty blanks under a "no" reads as a
    # form somebody failed to finish rather than one that was answered.
    disclosed = ""
    if said == "yes":
        disclosed = view._section("Disclosed Violation", (
            '<div class="fields">'
            + view._blank("Employer applied to", answer.get("prioremployer"), 6)
            + view._blank("Approximate test date", answer.get("priortestdate"), 6)
            + view._blank("Kind", KIND.get((answer.get("priortesttype") or "").lower()), 6)
            + view._blank("DOT return-to-duty requirements completed",
                          RTD.get((answer.get("priorrtd") or "").lower()), 6)
            + "</div>"
            # Said on the form, because the pages that follow are part of this document.
            + ('<p class="small">Return-to-duty or SAP paperwork was sent with this '
               'questionnaire and follows it.</p>' if answer.get("attached") else "")))

    # The certification, signed with the driver's own signature of record - the one they adopted on
    # their application. They proved who they are with their date of birth and SSN to answer at all.
    drawn = (view.signature_image(signature["typedname"], signature["fontkey"])
             if signature else None)
    stamp = " · ".join(filter(None, [
        "Signed electronically", (signature or {}).get("typedname"), view._t(signedon),
        f'IP {(signature or {}).get("ip") or "not recorded"}',
    ])) if signature else "Not signed"
    certification = (
        '<div class="section certify"><div class="bar">Applicant Certification</div>'
        f'<p>{view.escape(CERTIFY)}</p>'
        '<div class="avrow"><div class="avline">'
        + (f'<span class="avwritten"><img class="avsig" alt="Signature" src="{drawn}"></span>'
           if drawn else "")
        + '<span class="avcap">Signature of applicant</span></div>'
        + f'<div class="avline avshort"><span class="avval">{view._t(signedon)}</span>'
        + '<span class="avcap">Date signed</span></div></div>'
        + f'<p class="avstamp">{view.escape(stamp)}</p>'
        + "</div>")

    return f'<div class="sheet">{head}{applicant}{asked}{disclosed}{certification}</div>'


def keep(conn: Connection, accountid: str, driverid: str, answer: dict,
         requestid: str | None = None, attachment: bytes | None = None) -> str | None:
    """Render the answered questionnaire and file it as the document of record.

    Whatever the applicant sent with it - the SAP's determination, a return-to-duty result - is
    bound on as following pages rather than filed beside it. The driver filled in one form once,
    and a file that answers that with two rows makes the reader hold them together in their head."""
    driver = row(conn, """
        SELECT firstname, lastname, dob, licensenumber, licensestate
        FROM drivers WHERE recordid = :d
    """, d=driverid)
    account = row(conn, "SELECT name FROM accounts WHERE recordid = :a", a=accountid)
    if not driver or not account:
        return None
    signature = row(conn, """
        SELECT s.typedname, s.fontkey, ds.signedon, ds.ip
        FROM documentsignatures ds JOIN signatures s ON s.recordid = ds.signatureid
        WHERE ds.accountid = :a AND ds.ownertype = 'driver' AND ds.ownerid = :d
          AND ds.doctype = 'PREEMP_DA_QUESTIONNAIRE'
        ORDER BY ds.signedon DESC LIMIT 1
    """, a=accountid, d=driverid)
    html = build(answer, dict(driver), dict(account), dict(signature) if signature else None)
    pdf = images.bind([view.to_pdf({"html": html, "css": view.STYLE}, view.signature_css()),
                       attachment])
    documentid = storage.keep(conn, accountid, "documents", pdf,
                              "Pre-Employment Drug And Alcohol Questionnaire.pdf",
                              "application/pdf", None, origin=storage.DRIVER)
    if requestid:
        run(conn, "UPDATE uploadrequests SET documentid = :doc WHERE recordid = :id",
            doc=documentid, id=requestid)
    return documentid


__all__ = ["build", "keep", "QUESTION"]
