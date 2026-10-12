###################################################################################################
# The road test, rendered: the evaluation and - where the driver passed - the certificate 49 CFR
# 391.31(e) asks for, on one sheet.
#
# They are one document because they are one event. A certificate on its own says somebody formed
# an opinion; the evaluation behind it says what they saw. An auditor asking "on what basis" should
# not have to go and find a second file.
#
# A FAILED test still renders. It is a record of a test that happened, the driver is not qualified
# on it, and deleting it would leave the file saying nothing about an afternoon somebody spent
# finding out this person cannot reverse.
###################################################################################################
from sqlalchemy.engine import Connection

from app import applicationview as view
from app import roadtest, storage
from app.db import row, run

CERTIFY = (
    "This is to certify that the above-named driver was given a road test under my supervision on "
    "the date shown above, consisting of approximately the number of miles indicated. It is my "
    "considered opinion that this driver possesses sufficient driving skill to operate safely the "
    "type of commercial motor vehicle listed above."
)
EXAMINED = (
    "I certify that I have tested the above-named driver in accordance with 49 CFR 391.31 and that "
    "the road test was conducted in a vehicle representative of the type of motor vehicle the "
    "driver will operate."
)


def _day(value):
    return value.date() if hasattr(value, "date") else value


def _yesno(value):
    return "-" if value is None else ("Yes" if value else "No")


def _ratings(title: str, items, held: dict, note: str | None = None) -> str:
    body = view._rows([("Item", 74), ("Rating", 26)],
                      [[label, roadtest.RATINGS.get((held or {}).get(key), "-")]
                       for key, label in items], least=0)
    return view._section(title, (f'<p class="small">{view.escape(note)}</p>' if note else "") + body)


def build(test: dict, driver: dict, account: dict) -> str:
    name = f'{driver["firstname"]} {driver["lastname"]}'.strip().title()
    head = view._letterhead(account["name"], "Road Test Evaluation", name,
                            f'49 CFR 391.31 · {view._t(test.get("testedon"))}')

    who = view._section("Driver", (
        '<div class="fields">'
        + view._blank("Driver name", name, 6)
        + view._blank("Driver license no.", driver.get("licensenumber"), 6)
        + view._blank("Issuing state", driver.get("licensestate"), 6)
        + view._blank("Class", driver.get("licenseclass"), 6)
        + "</div>"))

    test_block = view._section("Road Test", (
        '<div class="fields">'
        + view._blank("Date", test.get("testedon"), 6)
        + view._blank("Approximate miles", test.get("miles"), 6)
        + view._blank("Started", test.get("startedat"), 6)
        + view._blank("Ended", test.get("endedat"), 6)
        + view._blank("Examiner", test.get("examinername"), 6)
        + view._blank("Title", test.get("examinertitle"), 6)
        + view._blank("Organization", test.get("examinerorg"), 12)
        + "</div>"))

    vehicle = view._section("Vehicle Used", (
        '<div class="fields">'
        + view._blank("Vehicle", test.get("vehicledescr"), 6)
        + view._blank("VIN", test.get("vin"), 6)
        + view._blank("Type", roadtest.VEHICLE_TYPES.get(test.get("vehicletype")), 6)
        + view._blank("GVWR", test.get("gvwr"), 6)
        + view._blank("Passenger capacity", test.get("seats"), 6)
        + view._blank("Air brakes", _yesno(test.get("airbrakes")), 6)
        + view._blank("Transmission", "Manual" if test.get("manual") else "Automatic", 6)
        + view._blank("Trailer", _yesno(test.get("trailer")), 6)
        + view._blank("Representative of the vehicle the driver will operate",
                      _yesno(test.get("representative")), 12)
        + "</div>"))

    federal = _ratings("Evaluation - 49 CFR 391.31(c)", roadtest.ITEMS, test.get("ratings"))
    extras = ""
    if any((test.get("extras") or {}).values()):
        extras = _ratings("Passenger Skills Evaluation", roadtest.EXTRAS, test.get("extras"),
                          "Company, state or contract requirements. Not part of 49 CFR 391.31.")

    remarks = view._section("Examiner Comments", (
        '<div class="fields">' + view._note("", test.get("comments"), 12) + "</div>"))

    drawn = (view.signature_image(test["certsignature"], test.get("certfontkey") or "modern")
             if test.get("certsignature") else None)
    stamp = " · ".join(filter(None, [
        "Signed electronically", test.get("certsignature"), view._t(test.get("completedon")),
        f'IP {test.get("completedip") or "not recorded"}',
    ]))
    passed = test.get("result") == "pass"
    decision = (
        '<div class="section certify"><div class="bar">'
        + ("Certificate Of Driver's Road Test" if passed else "Examiner's Decision")
        + "</div>"
        + f'<p><b>Result: {roadtest.RESULTS.get(test.get("result"), "Not decided")}</b></p>'
        + f'<p>{view.escape(CERTIFY if passed else EXAMINED)}</p>'
        + '<div class="fields">'
        + view._blank("Examiner", test.get("examinername"), 6)
        + view._blank("Title", test.get("examinertitle"), 6)
        + view._blank("Organization", test.get("examinerorg"), 6)
        + view._blank("Date", _day(test.get("completedon")), 6)
        + "</div>"
        + '<div class="avrow"><div class="avline">'
        + (f'<span class="avwritten"><img class="avsig" alt="Signature" src="{drawn}"></span>'
           if drawn else "")
        + '<span class="avcap">Signature of examiner</span></div>'
        + f'<div class="avline avshort"><span class="avval">'
        + f'{view._t(_day(test.get("completedon")))}</span>'
        + '<span class="avcap">Date</span></div></div>'
        + f'<p class="avstamp">{view.escape(stamp)}</p>'
        + "</div>")

    return (f'<div class="sheet">{head}{who}{test_block}{vehicle}{federal}{extras}'
            f'{remarks}{decision}</div>')


def keep(conn: Connection, recordid: str) -> str | None:
    """Render the completed test and file it as the document of record."""
    test = row(conn, "SELECT * FROM roadtests WHERE recordid = :i", i=recordid)
    if not test or not test.get("completedon"):
        return None
    held = dict(test)
    held["ratings"] = roadtest._parsed(held.get("ratings"))
    held["extras"] = roadtest._parsed(held.get("extras"))
    driver = row(conn, """
        SELECT d.firstname, d.lastname, l.number AS licensenumber, l.state AS licensestate,
               l.classification AS licenseclass
        FROM drivers d
        LEFT JOIN driverlicenses l ON l.driverid = d.recordid AND l.active = 1
        WHERE d.recordid = :d
    """, d=test["driverid"])
    account = row(conn, "SELECT name FROM accounts WHERE recordid = :a", a=test["accountid"])
    if not driver or not account:
        return None
    pdf = view.to_pdf({"html": build(held, dict(driver), dict(account)), "css": view.STYLE},
                      view.signature_css())
    documentid = storage.keep(conn, test["accountid"], "documents", pdf,
                              "Road test and certificate.pdf", "application/pdf", None, origin=storage.THIRDPARTY)
    run(conn, "UPDATE roadtests SET documentid = :doc WHERE recordid = :i",
        doc=documentid, i=recordid)
    return documentid


__all__ = ["build", "keep"]
