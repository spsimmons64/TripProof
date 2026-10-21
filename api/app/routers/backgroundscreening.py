"""Background screening, ordered from Certn - moved out of routers/vault.py, which grew too large to work in safely.

Shared helpers still live in vault and are imported from there."""
import hashlib
import io
import json
import logging
import re
import secrets
import zipfile
from datetime import date, datetime, time, timedelta
from html import escape

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import (accidents, annualreview, applicationview, backgroundchecks, billing,
                 invitations,
                 certn, documents, drivers,
                 eligibility, emails, exposure,
                 employers, events, gfeview, hos, i9, misreport, pdfform, randompool,
                 roadtest, roadtestview,
                 mvr as mvrs,
                 facts as factset, formats, images, mailer, phi, qualification, rules,
                 screening, screeningaccount, signatures, storage, tripcheck,
                 rates as rateset, vehicleclass, wheremap)
from app import dispatch, gateways, payerlines
from app.routers import signing, uploading
from app.activity import log
from app.config import settings
from app.db import get_conn, localnow, newid, row, rows, run, saved, utcnow
from app.evaluator import evaluate
from app.profiles import PROFILE_FIELDS, clean_profile
from app.routers import admin
from app.security import account_admin, client_ip, current_user, editor
from app.validity import credential_window
from app.routers.vault import (  # noqa: F401 - shared helpers
    ADVERSE_STATUS,
    _applicant,
    _blocking,
    _land_screening,
    _outcomes,
    _vendor,
    _vendor_token,
)

router = APIRouter(prefix="/api", tags=["vault"])


# ------------------------------------------------------------------------------------------------
# Background screening, ordered from Certn
# ------------------------------------------------------------------------------------------------

class ScreeningIn(BaseModel):
    reportsku: str
    addons: list[str] = []


# The add-ons an order can switch on, in the vendor's own words, with the SKU whose price applies
# when it is. Drug testing is deliberately absent: TripProof runs its own D&A programme with its
# own pools, records and rules, and buying a panel through a background check would put the same
# test in two places with two sets of paperwork.
SCREENING_ADDONS = {
    "mvr": ("The driving record", "mvr_with_surcharge"),
    "federal_criminal": ("Federal criminal search", "fedcrim"),
    "employment": ("Employment verification", "emp"),
    "education": ("Education verification", "edu"),
    "blj": ("Bankruptcies, liens and judgments", "blj"),
}


def _what_they_can_order(conn: Connection, accountid: str) -> dict:
    """The reports and add-ons on THIS company's account, at the prices they pay.

    Read from the vendor rather than from anything here. TripProof no longer sells screenings, so
    there is no price of ours to show - and a copy of theirs kept locally is a copy that goes
    stale the first time they change a price."""
    token = screeningaccount.token_for(conn, accountid)
    if not token:
        return {"reports": [], "addons": [], "problem": None}
    try:
        got = backgroundchecks.skus(token)
    except backgroundchecks.ScreeningError as e:
        return {"reports": [], "addons": [], "problem": str(e)}
    priced = {a["sku"]: a.get("price") for a in got.get("addons", [])}
    return {
        "reports": [{"sku": r["sku"], "name": r.get("title") or r["sku"],
                     "covers": r.get("description"), "price": r.get("price")}
                    for r in got.get("reports", [])],
        "addons": [{"flag": flag, "name": name, "price": priced.get(sku)}
                   for flag, (name, sku) in SCREENING_ADDONS.items() if sku in priced],
        "problem": None,
    }


def _vendor_error(name: str | None):
    return certn.CertnError if name == "certn" else backgroundchecks.ScreeningError


@router.get("/drivers/{driverid}/background")
def background_screening(driverid: str, user: dict = Depends(current_user),
                         conn: Connection = Depends(get_conn)):
    """What has been ordered for this driver, and what can be."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    catalogue = _what_they_can_order(conn, acct)
    return {
        # Whether THIS COMPANY can order, which means whether it holds an account of its own with
        # the vendor. Not whether this installation has credentials: ordering on our account would
        # make us the end user of a consumer report about somebody else's job applicant, which is
        # the one thing the whole arrangement exists to avoid.
        "available": screeningaccount.connected(conn, acct),
        # Which of the vendor's two worlds this installation talks to is a server fact. The
        # browser is told which script to load rather than working it out, so there is no second
        # place that can be pointed at production while the server is still on sandbox.
        "widgetscript": backgroundchecks.applicant_widget_script(),
        # The findings this requirement accepts, from the one place that decides what the server
        # will take - so a word the screen offers is never a word the server refuses.
        "outcomes": _outcomes("BACKGROUND_SCREENING"),
        # What this company may buy, from their own account. Not a price list of ours: TripProof
        # does not sell these and has nothing to quote.
        "reports": catalogue["reports"],
        "addons": catalogue["addons"],
        "skuproblem": catalogue["problem"],
        "orders": rows(conn, """
            SELECT r.recordid, r.tier, r.vendor, r.vendorstatus, r.inviteurl, r.vendorref,
                   r.chargecents, r.orderedon,
                   r.receivedon, r.issuedon, r.outcome, r.reviewstate, r.documentid, r.note,
                   u.name AS orderedbyname
            FROM driverreports r LEFT JOIN users u ON u.recordid = r.orderedby
            WHERE r.accountid = :a AND r.driverid = :d AND r.code = 'BACKGROUND_SCREENING'
            ORDER BY r.createdon DESC
        """, a=acct, d=driverid),
        # Where an open order has actually got to, inside itself. Asked live rather than stored,
        # because it changes at the vendor and a copy here would only ever be yesterday's answer.
        "progress": _screening_progress(conn, acct, driverid),
    }


def _screening_progress(conn: Connection, accountid: str, driverid: str) -> list[dict]:
    """What is finished inside the open order, and what is not."""
    held = row(conn, """
        SELECT vendorref FROM driverreports
        WHERE accountid = :a AND driverid = :d AND code = 'BACKGROUND_SCREENING'
          AND vendor = 'backgroundchecks' AND vendorref IS NOT NULL AND receivedon IS NULL
        ORDER BY createdon DESC LIMIT 1
    """, a=accountid, d=driverid)
    if not held:
        return []
    token = screeningaccount.token_for(conn, accountid)
    if not token:
        return []
    try:
        return backgroundchecks.progress(backgroundchecks.fetch(held["vendorref"], token)["raw"])
    except backgroundchecks.ScreeningError:
        # Not worth failing the page over: the order is still there and still says it is running.
        return []


@router.post("/drivers/{driverid}/background/order")
def order_background_screening(driverid: str, body: ScreeningIn, request: Request,
                               tasks: BackgroundTasks, user: dict = Depends(editor),
                               conn: Connection = Depends(get_conn)):
    """Order one screening on THIS COMPANY'S account with backgroundchecks.com.

    The order goes to the vendor first and nothing is written here until they hand back a
    reference: an order we cannot name is an order whose result can never be matched to a driver,
    and a row written before the call would be exactly that if the call then failed.

    No money moves through TripProof. The company holds the account, the vendor bills them, and
    the price recorded here is theirs - kept so the driver's file can say what was bought, not so
    that anybody can be charged for it."""
    acct = user["accountid"]
    driver = _applicant(conn, acct, driverid)
    token = screeningaccount.token_for(conn, acct)
    if not token:
        raise HTTPException(409, "This company has no account with backgroundchecks.com yet. Set "
                                 "one up under Company > Background Checks.")
    # Checked against what their account actually carries, not against a list we hold. A SKU this
    # company cannot buy is a 400 from them and a confusing afternoon for somebody here.
    catalogue = _what_they_can_order(conn, acct)
    report = next((r for r in catalogue["reports"] if r["sku"] == body.reportsku), None)
    if not report:
        raise HTTPException(400, "Choose one of the reports on this account")
    wanted = [a for a in body.addons if a in SCREENING_ADDONS]
    tier = {"name": report["name"], "reportsku": report["sku"],
            "products": ",".join(wanted)}
    # What the vendor will bill them, for the record on the driver's file.
    cost = (report.get("price") or 0) + sum(
        (a.get("price") or 0) for a in catalogue["addons"] if a["flag"] in wanted)
    # Not the date of birth. This vendor is never told it: they email the applicant a link and
    # the applicant enters their own details, their own SSN and their own authorisation, which is
    # whose they are to give. What the order does need is somewhere to send that email.
    if not (driver.get("email") or "").strip():
        raise HTTPException(409, "A background check is sent to the driver to fill in, so this "
                                 "driver needs an email address. Record it first.")
    open_already = row(conn, """
        SELECT recordid FROM driverreports
        WHERE accountid = :a AND driverid = :d AND code = 'BACKGROUND_SCREENING'
          AND receivedon IS NULL AND cancelledon IS NULL
    """, a=acct, d=driverid) if _has_cancelled() else row(conn, """
        SELECT recordid FROM driverreports
        WHERE accountid = :a AND driverid = :d AND code = 'BACKGROUND_SCREENING'
          AND receivedon IS NULL
    """, a=acct, d=driverid)
    if open_already:
        raise HTTPException(409, "A screening is already running for this driver")

    try:
        placed = backgroundchecks.order(tier, driver, driver.get("email"), token)
    except backgroundchecks.ScreeningError as e:
        raise HTTPException(502, str(e)) from e

    reportid = newid()
    # The order is already placed and already billable. If writing it down fails now, the worst
    # possible outcome is a quiet 500: the report exists at the vendor, the driver will be emailed
    # by them, and this office has no record that any of it happened. So the key goes into the
    # error itself, where somebody can read it and recover the order by hand.
    try:
        run(conn, """
            INSERT INTO driverreports (recordid, accountid, driverid, code, tier, vendor,
                                       vendorref, inviteurl, vendorstatus, chargecents,
                                       orderedon, orderedby, lastsyncedon)
            VALUES (:id, :a, :d, 'BACKGROUND_SCREENING', :t, 'backgroundchecks', :ref, :invite,
                    :st, :cents, :now, :by, :now)
        """, id=reportid, a=acct, d=driverid, t=body.reportsku, ref=placed["ref"],
            invite=(placed.get("invite") or None), st=placed["status"], cents=cost,
            now=utcnow(), by=user["recordid"])
    except Exception as e:                                            # noqa: BLE001 - see above
        logging.getLogger("tripproof.vault").error(
            "screening ORDERED BUT NOT RECORDED driver=%s ref=%s invite=%s: %s",
            driverid, placed["ref"], placed.get("invite"), e)
        raise HTTPException(500,
            f"The screening was ordered at backgroundchecks.com - their reference is "
            f"{placed['ref']} - but it could not be written to this driver's file, so nothing "
            f"here knows about it. Quote that reference to support; do not order it again.") from e

    # Tell the driver where to go, ourselves.
    #
    # The vendor emails them too, and in production that usually arrives. But a screening that
    # depends entirely on a stranger's email is a screening that stalls silently: the driver gets
    # nothing, the office sees "waiting on the driver" for a week, and nobody can say whether the
    # email was sent, binned or never addressed. TripProof already asks drivers for documents and
    # signatures in its own post - this goes the same way, from the company they actually work
    # for, and the link is returned so the office can read it out to somebody with no email.
    invite = placed.get("invite")
    sentto = None
    if invite and (driver.get("email") or "").strip():
        company = (row(conn, "SELECT name FROM accounts WHERE recordid = :a", a=acct)
                   or {}).get("name") or "Your employer"
        subject, html, text = emails.screening_invited(
            name=f'{driver["firstname"]} {driver["lastname"]}'.strip(), accountname=company,
            tier=report["name"], link=invite)
        sentto = driver["email"]
        tasks.add_task(mailer.send, sentto, subject, html, text)

    log(conn, user, "order", "driverreport", driverid,
        {"code": "BACKGROUND_SCREENING", "reportsku": body.reportsku, "addons": wanted,
         "cents": cost, "invited": sentto}, ip=client_ip(request))
    saved(conn)
    return {"ok": True, "recordid": reportid, "link": invite, "sentto": sentto}


def _has_cancelled() -> bool:
    """Older installations have no `cancelledon` on this table."""
    return False


@router.post("/drivers/{driverid}/background/{recordid}/refresh")
def refresh_background_screening(driverid: str, recordid: str, request: Request,
                                 user: dict = Depends(editor),
                                 conn: Connection = Depends(get_conn)):
    """Ask the vendor where an order has got to, rather than waiting to be told.

    backgroundchecks.com publishes no webhook, so for those this is the ONLY way a result arrives.
    For a vendor that does post one, this is the answer to a webhook that went missing: an office
    with a driver waiting should never be stuck because a callback was lost."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    held = row(conn, """
        SELECT recordid, vendor, vendorref, vendorstatus FROM driverreports
        WHERE recordid = :id AND accountid = :a AND driverid = :d
    """, id=recordid, a=acct, d=driverid)
    if not held or not held["vendorref"]:
        raise HTTPException(404, "No such order")
    with_ = _vendor(held["vendor"])
    try:
        got = with_.fetch(held["vendorref"], **_vendor_token(conn, acct, held["vendor"]))
    except _vendor_error(held["vendor"]) as e:
        raise HTTPException(502, str(e)) from e
    _land_screening(conn, acct, driverid, held["recordid"], held["vendorref"], got["status"],
                    held["vendor"])
    log(conn, user, "order", "driverreport", driverid,
        {"code": "BACKGROUND_SCREENING", "checked": got["status"]}, ip=client_ip(request))
    saved(conn)
    return {"ok": True, "status": got["status"]}


@router.get("/trips/upcoming")
def upcoming_trips(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """The next trips on the book, and whether the people and vehicles on them may actually run.

    This is the whole point of the application in one list. A driver whose medical certificate
    lapsed is an abstraction until it is a named passenger on Thursday, and a compliance file that
    cannot answer "is tomorrow covered" is a filing cabinet."""
    acct = user["accountid"]
    today = localnow(user["timezone"]).date()
    trips = rows(conn, """
        SELECT t.recordid, t.externalid, t.tripdate, t.servicelevel,
               COUNT(l.recordid) AS legs,
               SUM(l.pickupat IS NOT NULL) AS started,
               SUM(l.dropoffat IS NOT NULL) AS finished,
               GROUP_CONCAT(DISTINCT CONCAT(COALESCE(d.firstname, ''), ' ',
                                            COALESCE(d.lastname, '')) SEPARATOR ', ') AS drivers,
               GROUP_CONCAT(DISTINCT d.recordid) AS driverids,
               GROUP_CONCAT(DISTINCT COALESCE(v.externalid, v.vin) SEPARATOR ', ') AS vehicles,
               GROUP_CONCAT(DISTINCT v.recordid) AS vehicleids
        FROM trips t
          LEFT JOIN triplegs l ON l.tripid = t.recordid
          LEFT JOIN drivers d ON d.recordid = l.driverid AND d.deleted IS NULL
          LEFT JOIN vehicles v ON v.recordid = l.vehicleid AND v.deleted IS NULL
        WHERE t.accountid = :a AND t.deleted IS NULL AND t.tripdate >= :from
        GROUP BY t.recordid, t.externalid, t.tripdate, t.servicelevel
        ORDER BY t.tripdate, t.externalid
        LIMIT 12
    """, a=acct, **{"from": today - timedelta(days=3)})
    if not trips:
        return {"trips": [], "from": str(today)}

    # Who cannot drive and what cannot go out, worked out once for the whole list rather than once
    # per trip - the same engine the dashboard and the roster read.
    stopped, grounded = set(), set()
    for d in {x for t in trips for x in (t["driverids"] or "").split(",") if x}:
        hired = row(conn, "SELECT hiredon FROM drivers WHERE recordid = :d", d=d) or {}
        if not hired.get("hiredon"):
            stopped.add(d)
            continue
        if any(i["applies"] is True and i["gate"] == "hardstop"
               and i["status"] in (*ADVERSE_STATUS, "pending")
               for i in rules.for_driver(conn, acct, d,
                                         factset.assemble(conn, acct, d)["facts"], today=today)):
            stopped.add(d)
    for v in {x for t in trips for x in (t["vehicleids"] or "").split(",") if x}:
        if any(i["applies"] is True and i["gate"] == "hardstop"
               and i["status"] in (*ADVERSE_STATUS, "pending")
               for i in rules.for_vehicle(conn, acct, v,
                                          factset.assemble(conn, acct, vehicleid=v)["facts"],
                                          today=today)):
            grounded.add(v)

    out = []
    for t in trips:
        ds = [x for x in (t["driverids"] or "").split(",") if x]
        vs = [x for x in (t["vehicleids"] or "").split(",") if x]
        # Where the trip itself has got to. Read from the legs rather than stored, so it cannot
        # disagree with them: a trip is under way when a leg has been picked up and finished when
        # every leg has been dropped off.
        if not ds or not vs:
            state = "Unassigned"
        elif t["finished"] and t["finished"] == t["legs"]:
            state = "Completed"
        elif t["started"]:
            state = "In progress"
        else:
            state = "Upcoming"
        out.append({
            "recordid": t["recordid"], "externalid": t["externalid"],
            "tripdate": t["tripdate"], "servicelevel": t["servicelevel"],
            "drivers": (t["drivers"] or "").strip() or None,
            "vehicles": t["vehicles"] or None,
            "state": state,
            # Whether the people and vehicles on it may actually run. Carried beside the trip's own
            # state rather than instead of it: a trip can be perfectly scheduled for tomorrow and
            # still have a driver who may not drive.
            "driverbarred": any(d in stopped for d in ds),
            "vehiclebarred": any(v in grounded for v in vs),
        })
    return {"trips": out, "from": str(today)}


# What the first screen anybody opens has to say. Until this existed the dashboard showed arriving
# documents and nothing else, so an office could open TripProof, read "nothing is waiting", and not
# know its auto liability had lapsed or that the plan needed certifying next month. A thing nobody
# has to touch today still has to be visible before the day it stops the company.
@router.get("/attention")
def needs_attention(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Everything across the company, its drivers and its fleet that wants somebody.

    Three lists rather than one number: what is stopping something today, what is overdue or
    missing, and what runs out soon. A count on its own tells nobody what to do."""
    acct = user["accountid"]
    today = localnow(user["timezone"]).date()
    stops, owed, soon, toread = [], [], [], []
    roster, units = [], []

    def sort(where, who, link, items, since=None):
        for i in items:
            if i["applies"] is not True:
                continue
            # Nothing that starts at hiring is owed by somebody nobody has hired. The driver's own
            # page says so by grouping the list into stages; a dashboard that flattens it was
            # telling an office an applicant owed a W-4.
            if since is False and i.get("duestage") in ("athire", "ongoing"):
                continue
            # And nothing about somebody nobody has hired STOPS WORK. An applicant is not driving,
            # so an incomplete file of theirs stands between them and a hire - it does not stop the
            # business. It is outstanding, and it is the hiring screen's job, not the verdict's.
            stopping = i["gate"] == "hardstop" and since is not False
            joiner = "&" if "?" in link else "?"
            row_ = {"where": where, "who": who, "link": f'{link}{joiner}req={i["code"]}',
                    "code": i["code"], "name": i["name"], "why": i["why"],
                    "status": i["status"], "on": i["expireson"]}
            if i["status"] == "review":
                toread.append(row_)
            elif i["status"] in ("failed", "expired", "overdue"):
                (stops if stopping else owed).append(row_)
            elif i["status"] == "pending" and stopping:
                stops.append(row_)
            elif i["status"] == "pending":
                owed.append(row_)
            elif i["status"] == "expiring" and not i.get("scheduled"):
                # A monthly exclusion screening renews itself. Putting its routine turn beside an
                # expired medical certificate is how a dashboard teaches people to ignore it.
                soon.append(row_)

    company = factset.assemble(conn, acct)
    # The link carries the requirement, not just the page it is on. A dashboard that names a
    # problem and then hands somebody the page to go and find it on is a list of complaints.
    sort("company", None, "/company?tab=requirements",
         rules.for_company(conn, acct, company["facts"], today=today))

    for d in rows(conn, """
        SELECT recordid, firstname, lastname, hiredon FROM drivers
        WHERE accountid = :a AND deleted IS NULL AND stub = 0 AND terminatedon IS NULL
        ORDER BY lastname, firstname
    """, a=acct):
        who = f'{d["firstname"]} {d["lastname"]}'.strip().title()
        items = rules.for_driver(conn, acct, d["recordid"],
                                 factset.assemble(conn, acct, d["recordid"])["facts"], today=today)
        sort("driver", who, f'/drivers/{d["recordid"]}', items, since=bool(d["hiredon"]))
        # Whether this person may drive today, which is a different question from whether their
        # file is complete: an applicant with a perfect file still may not drive, because nobody
        # has hired them.
        barred = [i for i in items if i["applies"] is True and i["gate"] == "hardstop"
                  and i["status"] in (*ADVERSE_STATUS, "pending")]
        roster.append({
            "recordid": d["recordid"], "name": who, "link": f'/drivers/{d["recordid"]}',
            "hired": bool(d["hiredon"]),
            "eligible": bool(d["hiredon"]) and not barred,
            "why": ("Not hired yet" if not d["hiredon"] else _blocking(barred, "Clear to drive")),
        })

    for v in rows(conn, """
        SELECT recordid, externalid, vin, make, model FROM vehicles
        WHERE accountid = :a AND deleted IS NULL AND stub = 0 ORDER BY externalid, vin
    """, a=acct):
        who = v["externalid"] or v["vin"] or " ".join(
            x for x in (v["make"], v["model"]) if x) or "A vehicle"
        items = rules.for_vehicle(conn, acct, v["recordid"],
                                  factset.assemble(conn, acct, vehicleid=v["recordid"])["facts"],
                                  today=today)
        sort("vehicle", who, f'/vehicles/{v["recordid"]}', items)
        barred = [i for i in items if i["applies"] is True and i["gate"] == "hardstop"
                  and i["status"] in (*ADVERSE_STATUS, "pending")]
        units.append({
            "recordid": v["recordid"], "name": who, "link": f'/vehicles/{v["recordid"]}',
            "eligible": not barred,
            "why": _blocking(barred, "Ready to dispatch"),
        })

    # Soonest first, because that is the order somebody works them in.
    soon.sort(key=lambda r: r["on"] or date.max)

    # How many of each are clear, so the headline is a fraction somebody can act on rather than a
    # total they have to count themselves.
    stopped = {r["who"] for r in stops if r["where"] == "driver"}
    grounded = {r["who"] for r in stops if r["where"] == "vehicle"}
    drivers = rows(conn, """
        SELECT COUNT(*) AS n FROM drivers WHERE accountid = :a AND deleted IS NULL AND stub = 0
          AND terminatedon IS NULL AND hiredon IS NOT NULL""", a=acct)[0]["n"]
    applicants = rows(conn, """
        SELECT COUNT(*) AS n FROM drivers WHERE accountid = :a AND deleted IS NULL AND stub = 0
          AND terminatedon IS NULL AND hiredon IS NULL""", a=acct)[0]["n"]
    fleet = rows(conn, """
        SELECT COUNT(*) AS n FROM vehicles WHERE accountid = :a AND deleted IS NULL AND stub = 0
    """, a=acct)[0]["n"]
    return {
        "stops": stops, "owed": owed, "soon": soon, "toread": toread,
        "roster": roster, "fleet": units,
        "summary": {
            "company": len([r for r in stops if r["where"] == "company"]),
            "drivers": drivers, "driversclear": drivers - len(stopped),
            "applicants": applicants,
            "vehicles": fleet, "vehiclesclear": fleet - len(grounded),
        },
    }


@router.get("/company/requirements")
def company_requirements(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """What is asked of the company itself, and where it stands on each of it.

    The same engine the driver screen reads. Nothing here is stored: the rules come from the
    catalog, the facts from what the company has said about itself, and the evidence from the
    documents already on file - so this cannot drift out of step with the filing cabinet."""
    acct = user["accountid"]
    gathered = factset.assemble(conn, acct)
    items = rules.for_company(conn, acct, gathered["facts"],
                              today=localnow(user["timezone"]).date())
    counted: dict[str, int] = {}
    for i in items:
        counted[i["status"]] = counted.get(i["status"], 0) + 1
    live = [i for i in items if i["applies"] is True]
    return {"items": items, "counts": counted,
            # What is actually wrong, as against what is merely on the list.
            "outstanding": [i["code"] for i in live
                            if i["status"] in ("pending", "expired", "failed", "overdue")],
            "stops": [i["code"] for i in live
                      if i["gate"] == "hardstop"
                      and i["status"] in ("pending", "expired", "failed", "overdue")],
            "types": {r["code"]: r["recordid"] for r in rows(conn, """
                SELECT code, recordid FROM credentialtypes
                WHERE subject = 'company' AND active = 1""")}}
