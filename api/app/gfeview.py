###################################################################################################
# The good faith effort, as the document it has to be - 49 CFR 391.23(i).
#
# What an auditor asks for when the previous employer never answered is not a status word. It is a
# page saying who was asked, everything that was tried and when, how the investigation ended, and
# whose signature stands behind that. The screen holds all of it; this is that screen rendered onto
# the carrier's letterhead and kept, so the record survives the screen.
#
# It is drawn at the moment it is certified, from the same sheets and signature faces the
# application and the SPHI reply use - not rebuilt later from columns somebody may have edited
# since. What is kept is what the person signed.
###################################################################################################
from sqlalchemy.engine import Connection

from app import applicationview as view
from app import employers, storage
from app.db import row, rows, run

CERTIFY = (
    "I certify that the employer made a good faith effort to obtain the driver's required safety "
    "performance history from the previous employer identified above. The attempts documented in "
    "this record represent the actions taken to obtain the required information."
)


def _day(value):
    return value.date() if hasattr(value, "date") else value


def build(inq: dict, driver: dict, account: dict, tried: list[dict]) -> str:
    """The whole effort as one sheet, in the order the form asks it."""
    name = f'{driver["firstname"]} {driver["lastname"]}'.strip().title()
    head = view._letterhead(
        account["name"], "Safety Performance History Investigation", name,
        f'Good faith effort documentation · {view._t(_day(inq.get("effortclosedon")))}')

    person = view._section("Driver", (
        '<div class="fields">'
        + view._blank("Driver name", name, 6)
        + view._blank("Driver ID", driver.get("drivernumber"), 6)
        + view._blank("Date of hire", driver.get("hiredon"), 6)
        + view._blank("Date of birth", driver.get("dob"), 6)
        + "</div>"))

    previous = view._section("Previous Employer", (
        '<div class="fields">'
        + view._blank("Employer", inq["employer"], 6)
        + view._blank("Contact", inq.get("contactname"), 6)
        + view._blank("Phone", inq.get("phone"), 6)
        + view._blank("Email", inq.get("email"), 6)
        + view._blank("Fax", inq.get("fax"), 6)
        + view._blank("Employed", " to ".join(
            [str(x) for x in (inq.get("employedfrom"), inq.get("employedthrough")) if x]), 6)
        + "</div>"))

    # Every attempt, which is what the effort IS. 391.23(i) counts the asking, so the asking is
    # printed in full rather than summarised as a number.
    attempts = view._section(f"Attempts ({len(tried)})", view._rows(
        [("Date", 18), ("Method", 18), ("Sent to", 32), ("Result", 32)],
        [[_day(a.get("senton")), employers.CHANNELS.get(a.get("channel"), a.get("channel")),
          a.get("sentto"), " - ".join(x for x in (a.get("outcome"), a.get("note")) if x)]
         for a in tried],
        least=1))

    ending = employers.GFE_STATUS.get(inq.get("effortstatus") or "noresponse")
    determination = view._section("Determination", (
        '<div class="fields">'
        + view._blank("Outcome", ending, 12)
        + "</div>"
        + ('<div class="fields">' + view._note("Notes", inq.get("effortnote"), 12) + "</div>"
           if inq.get("effortnote") else "")))

    drawn = (view.signature_image(inq["effortsignature"], inq.get("effortfontkey") or "modern")
             if inq.get("effortsignature") else None)
    stamp = " · ".join(filter(None, [
        "Signed electronically", inq.get("effortsignature"),
        view._t(inq.get("effortsignedon")),
    ])) if inq.get("effortsignature") else "Not signed"
    certification = (
        '<div class="section certify"><div class="bar">Certification</div>'
        f'<p>{view.escape(CERTIFY)}</p>'
        '<div class="fields">'
        + view._blank("Completed by", inq.get("certifiername"), 6)
        + view._blank("Title", inq.get("certifiertitle"), 6)
        + "</div>"
        + '<div class="avrow"><div class="avline">'
        + (f'<span class="avwritten"><img class="avsig" alt="Signature" src="{drawn}"></span>'
           if drawn else "")
        + '<span class="avcap">Signature</span></div>'
        + f'<div class="avline avshort"><span class="avval">'
        + f'{view._t(_day(inq.get("effortsignedon")))}</span>'
        + '<span class="avcap">Completion date</span></div></div>'
        + f'<p class="avstamp">{view.escape(stamp)}</p>'
        + "</div>")

    return (f'<div class="sheet">{head}{person}{previous}{attempts}'
            f'{determination}{certification}</div>')


def keep(conn: Connection, inquiryid: str, certifier: dict | None = None) -> str | None:
    """Render the certified effort and file it as the document of record."""
    inq = row(conn, "SELECT * FROM employerinquiries WHERE recordid = :i", i=inquiryid)
    if not inq or not inq.get("effortclosedon"):
        return None
    driver = row(conn, """
        SELECT firstname, lastname, dob, drivernumber, hiredon FROM drivers WHERE recordid = :d
    """, d=inq["driverid"])
    account = row(conn, "SELECT name FROM accounts WHERE recordid = :a", a=inq["accountid"])
    if not driver or not account:
        return None
    tried = rows(conn, """
        SELECT channel, sentto, senton, outcome, note FROM employerinquiryattempts
        WHERE inquiryid = :i ORDER BY senton
    """, i=inquiryid)
    held = {**dict(inq),
            "certifiername": (certifier or {}).get("name"),
            "certifiertitle": (certifier or {}).get("role")}
    html = build(held, dict(driver), dict(account), tried)
    pdf = view.to_pdf({"html": html, "css": view.STYLE}, view.signature_css())
    documentid = storage.keep(conn, inq["accountid"], "documents", pdf,
                              f'Good faith effort - {inq["employer"]}.pdf',
                              "application/pdf", None, origin=storage.THIRDPARTY)
    run(conn, "UPDATE employerinquiries SET effortdocumentid = :doc WHERE recordid = :i",
        doc=documentid, i=inquiryid)
    return documentid


__all__ = ["build", "keep"]
