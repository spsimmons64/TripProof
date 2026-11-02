"""Billing: every finished trip priced, the clean ones ready to bill, the rest said why not.

Nobody has to open a clean trip. A finished trip is priced under the fee schedule in force on its
date and is Ready - unless something needs a person, when it is an Exception with the reason. A
person can clear what is a judgement (no signature, no GPS trail); what must be settled first (an
open problem, a dispute, a failed requirement) cannot be cleared.

Priced live until it is billed. Billing writes the charge lines, each with the rate that produced
it: into a numbered batch per broker, or a numbered invoice per private-pay trip.

Miles are the GPS trail with the passenger aboard; the driver's figure only where there is no trail.
"""

import csv
import io
import secrets
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import applicationview as view
from app import dispatch, emails, gateways, mailer, phi, rates, tripcheck, wheremap
from app.activity import log
from app.config import settings
from app.db import engine, get_conn, localnow, newid, row, rows, run, saved, utcnow
from app.routers.places import full
from app.routers.trips import _as_instant
from app.security import client_ip, current_user, editor

router = APIRouter(prefix="/api/trip-billing", tags=["tripbilling"])

# Finished: no leg is still to happen, and there is something that may be owed for.
FINISHED = """
    t.deleted IS NULL AND t.cancelledon IS NULL AND t.brokerstate <> 'returned'
    AND NOT EXISTS (SELECT 1 FROM triplegs o WHERE o.tripid = t.recordid AND o.executionstate <> 'completed'
                     AND o.outcomestate IS NULL AND COALESCE(o.brokerstate, '') <> 'returned')
    AND EXISTS (SELECT 1 FROM triplegs o WHERE o.tripid = t.recordid
                 AND (o.executionstate = 'completed' OR o.outcomestate IN ('noshow', 'disputed')))
"""
CENT = Decimal("0.01")


ORDER_LINES = "added, LEFT(label, 5), label LIKE '%base fare%' DESC, label"     # by leg, the fare first


def _money(v) -> Decimal:
    return Decimal(str(v)).quantize(CENT, ROUND_HALF_UP)


def _rounded(miles: Decimal, how: str | None) -> Decimal:
    if how == "whole":
        return miles.quantize(Decimal("1"), ROUND_HALF_UP)
    if how == "none":
        return miles
    return miles.quantize(Decimal("0.1"), ROUND_HALF_UP)


def _code(r: dict) -> str | None:
    return " ".join(x for x in (r["proceduracode"], r["modifier"]) if x) or None


def _waited(minutes: int, r: dict) -> Decimal:
    """The billable units in a wait. Included units are the rate's own: two blocks of fifteen minutes
    is the first half hour free; a part block counts as a whole one."""
    free = Decimal(str(r["includedunits"] or 0))
    if r["unit"] == "block15":
        units = (Decimal(minutes) / 15).to_integral_value(ROUND_CEILING)
    else:
        units = Decimal(minutes) / 60 if r["unit"] == "hour" else Decimal(minutes)
    return max(Decimal(0), units - free)


def price(conn: Connection, acct: str, trip: dict, legs: list[dict]) -> dict:
    """The trip's charge lines under the schedule in force on its date, or why there are none."""
    start = next((l["pickupplace"] for l in legs if l["pickupplace"]), None)
    card = rates.in_force(conn, acct, payerid=trip["brokerid"], on=trip["tripdate"], state=tripcheck.pickup_state(start))
    if not card:
        return {"lines": [], "amount": Decimal("0"), "scheduleid": None, "usesmiles": False, "why": "No fee schedule is in force for this payer on this date."}
    mine = [r for r in rows(conn, "SELECT * FROM payerrates WHERE scheduleid = :s ORDER BY sortorder, ratetype", s=card["recordid"])
            if (r["servicelevel"] or "") in ("", trip["servicelevel"])]
    pick = lambda kind: next((r for r in mine if r["ratetype"] == kind), None)  # noqa: E731
    lines = []

    def add(leg, label, r, units):
        lines.append({"legid": leg and leg["legid"], "label": label, "code": _code(r), "units": units, "rate": _money(r["amount"]),
                      "amount": _money(Decimal(units) * Decimal(str(r["amount"]))), "rateid": r["recordid"]})
    flat, base, mileage, wait, noshow = pick("flat"), pick("base"), pick("mileage"), pick("waiting"), pick("noshow")
    driven = [l for l in legs if l["driven"]]
    once = {"flat": False, "base": False}
    for l in legs:
        name = f"Leg {l['legnumber']}"
        if l["outcome"] == "noshow":
            if noshow:
                add(l, f"{name} no-show", noshow, Decimal(1))
            continue
        if not l["driven"]:
            continue
        if flat:
            if flat["unit"] == "leg" or not once["flat"]:
                add(l, f"{name} flat rate" if flat["unit"] == "leg" else "Flat trip rate", flat, Decimal(1))
                once["flat"] = True
            continue
        if base and (base["unit"] == "leg" or not once["base"]):
            free = int(mileage["includedunits"] or 0) if mileage else 0
            add(l, f"{name} base fare" + (f", first {free} miles included" if free else ""), base, Decimal(1))
            once["base"] = True
        if mileage and l["miles"] is not None:
            miles = _rounded(Decimal(str(l["miles"])), mileage["rounding"])
            over = max(Decimal(0), miles - Decimal(str(mileage["includedunits"] or 0)))
            if mileage["minimumunits"] is not None:
                over = max(over, Decimal(str(mileage["minimumunits"])))
            if over > 0:
                add(l, f"{name} loaded miles", mileage, over)
        if wait and l["waitminutes"]:
            units = _waited(l["waitminutes"], wait)
            if units > 0:
                add(l, f"{name} waiting {l['waitminutes']} minutes", wait, units)
    for s in (r for r in mine if r["ratetype"] == "surcharge"):
        if driven:
            add(None, s["name"] or "Surcharge", s, Decimal(1 if s["unit"] != "leg" else len(driven)))
    return {"lines": lines, "amount": sum((x["amount"] for x in lines), Decimal("0")), "scheduleid": card["recordid"], "usesmiles": bool(mileage and not flat),
            "why": None if lines else "The fee schedule prices nothing for this service."}


def _legs(conn: Connection, acct: str, tripid: str) -> list[dict]:
    zone = dispatch.zone(conn, acct)
    out = []
    for l in rows(conn, """
        SELECT l.recordid, l.legnumber, l.pickupat, l.pickupplace, l.dropoffplace, l.executionstate, l.outcomestate, l.brokerstate,
               l.driverid, l.miles, l.officemiles, l.officemilesreason, l.signature, l.selfassignedon, l.afterhoursreviewedon,
               TRIM(CONCAT(d.firstname, ' ', d.lastname)) AS drivername, v.externalid AS vehiclename
        FROM triplegs l LEFT JOIN drivers d ON d.recordid = l.driverid LEFT JOIN vehicles v ON v.recordid = l.vehicleid
        WHERE l.tripid = :t AND l.accountid = :a ORDER BY l.legnumber
    """, t=tripid, a=acct):
        said = {e["state"]: e["at"] for e in rows(conn, "SELECT state, MIN(happenedon) AS at FROM tripevents WHERE legid = :l GROUP BY state", l=l["recordid"])}
        driven = l["executionstate"] == "completed"
        began = said.get("onboard") or (_as_instant(l["pickupat"], zone) if l["pickupat"] else None)
        miles, source = None, None
        if driven and l["driverid"] and began and said.get("completed"):
            trail = wheremap.trail_miles(conn, acct, l["driverid"], began, said["completed"])
            if trail["fixes"] >= 2 and trail["miles"] > 0:
                miles, source = trail["miles"], "GPS"
        if driven and miles is None and l["miles"] is not None:
            miles, source = float(l["miles"]), "Driver"
        if driven and l["officemiles"] is not None:
            miles, source = float(l["officemiles"]), "Office"
        waits = rows(conn, "SELECT endedon, TIMESTAMPDIFF(MINUTE, startedon, COALESCE(endedon, startedon)) AS minutes FROM tripwaits WHERE legid = :l", l=l["recordid"])
        out.append({"legid": l["recordid"], "legnumber": l["legnumber"], "pickupplace": l["pickupplace"], "dropoffplace": l["dropoffplace"],
                    "drivername": l["drivername"], "vehiclename": l["vehiclename"], "aboardat": said.get("onboard"), "droppedat": said.get("completed"),
                    "miles": miles, "milessource": source, "milesreason": l["officemilesreason"], "waitminutes": sum(w["minutes"] or 0 for w in waits),
                    "openwait": any(w["endedon"] is None for w in waits), "signature": bool(l["signature"]), "driven": driven,
                    "outcome": l["outcomestate"], "afterhours": bool(l["selfassignedon"] and not l["afterhoursreviewedon"]),
                    "state": {"cancelled": "Canceled", "noshow": "No-Show", "aborted": "Not Done By Us", "disputed": "In Dispute"}.get(l["outcomestate"])
                    or ("Returned To Broker" if l["brokerstate"] == "returned" else "Driven" if driven else "Not Driven")})
    return out


def _read(conn: Connection, acct: str, trip: dict) -> dict:
    """A trip as billing sees it: priced, and what stands in the way - `stops` must be settled;
    `reasons` a person can clear."""
    legs = _legs(conn, acct, trip["recordid"])
    stops, reasons = [], []
    for l in legs:
        name = f"Leg {l['legnumber']}"
        if l["afterhours"]:
            stops.append(f"{name} was taken on call after closing and has not had its After-Hours Review.")
        if l["driven"]:
            if l["milessource"] == "Driver":
                reasons.append(f"{name} has no GPS trail; {l['miles']:.1f} miles is the driver's figure.")
            if not l["signature"]:
                reasons.append(f"{name} has no signature.")
        if l["openwait"]:
            reasons.append(f"{name} has a wait that was never ended.")
        if l["outcome"] == "noshow":
            reasons.append(f"{name} was a no-show: bill it only if the contract pays one.")
    for i in rows(conn, "SELECT note, kind FROM tripissues WHERE tripid = :t AND resolvedon IS NULL", t=trip["recordid"]):
        stops.append(f"A problem the driver reported is still open: {i['note'] or i['kind']}.")
    for d in rows(conn, "SELECT reason FROM tripdisputes WHERE tripid = :t AND settledon IS NULL", t=trip["recordid"]):
        stops.append(f"A dispute is not settled: {d['reason']}.")
    if trip["lastrunid"]:
        for c in rows(conn, "SELECT DISTINCT rulename, reason FROM legchecks WHERE tripid = :t AND runid = :r AND outcome = 'fail' AND COALESCE(approved, 1) = 1",
                      t=trip["recordid"], r=trip["lastrunid"]):
            stops.append(f"Failed requirement: {c['rulename'] or 'a requirement'}{' - ' + c['reason'] if c['reason'] else ''}.")
    priced = price(conn, acct, trip, legs)
    if priced["why"]:
        stops.append(priced["why"])
    # Billed with no miles, the mileage charge is simply lost: they are entered first.
    if priced["usesmiles"]:
        stops += [f"Leg {l['legnumber']} has no miles. Enter them with Correct Miles." for l in legs if l["driven"] and l["miles"] is None]
    held = trip["verifystate"] == "needscorrection" or trip["billingstatus"] == "held"
    if trip["verifystate"] == "verified" and not held:
        reasons = []                               # a person has looked, and cleared them
    if held:
        reasons.insert(0, trip["holdreason"] or "On hold.")
    return {"legs": legs, "stops": stops, "reasons": reasons, "priced": priced}


TRIP = """
    SELECT t.recordid, t.externalid, t.tripdate, t.passenger, t.servicelevel, t.brokerid, t.verifystate, t.billingstatus,
           t.holdreason, t.lastrunid, t.billedamount, t.billbatchid, COALESCE(b.name, 'Private Pay') AS payer,
           bb.number AS batchnumber, bb.createdon AS batchedon, t.billinvoiceid, inv.number AS invoicenumber,
           inv.billtoemail, inv.emailedon, inv.emailerror,
           COALESCE(bb.createdon, inv.createdon) AS billedon, inv.remindercount, inv.lastremindedon,
           (SELECT COALESCE(SUM(p.amount), 0) FROM billpayments p WHERE p.tripid = t.recordid AND p.denied = 0 AND p.voidedon IS NULL) AS paid,
           (SELECT COALESCE(SUM(p.writedown), 0) FROM billpayments p WHERE p.tripid = t.recordid AND p.denied = 0 AND p.voidedon IS NULL) AS writedown,
           (SELECT COALESCE(SUM(p.writedown), 0) FROM billpayments p WHERE p.tripid = t.recordid AND p.refund = 1 AND p.voidedon IS NULL) AS refunded
    FROM trips t LEFT JOIN payers b ON b.recordid = t.brokerid LEFT JOIN billbatches bb ON bb.recordid = t.billbatchid
    LEFT JOIN tripinvoices inv ON inv.recordid = t.billinvoiceid
"""


def _unbilled(conn: Connection, acct: str) -> list[dict]:
    """Every finished trip not billed yet, read: so ready and exceptions are always true as of now."""
    out = rows(conn, f"{TRIP} WHERE t.accountid = :a AND t.billingstatus IN ('unbilled', 'held') AND {FINISHED} ORDER BY t.tripdate, t.externalid", a=acct)
    for t in out:
        t.update(_read(conn, acct, t))
    return out


def _row(t: dict) -> dict:
    keep = ("recordid", "externalid", "tripdate", "passenger", "payer", "brokerid", "billingstatus", "batchnumber", "batchedon", "invoicenumber")
    said = (t.get("stops") or []) + (t.get("reasons") or [])
    return {**{k: t[k] for k in keep}, "amount": float(t["priced"]["amount"]) if t.get("priced") else float(t["billedamount"] or 0),
            "paid": float(t["paid"] or 0), "writedown": float(t["writedown"] or 0) - float(t["refunded"] or 0), "refunded": float(t["refunded"] or 0),
            "owing": float(_owing(t)) if not t.get("priced") else None, "billedon": t["billedon"],
            "age": (utcnow() - t["billedon"]).days if t["billedon"] else None, "miles": round(sum(l["miles"] or 0 for l in t["legs"]), 1) if t.get("legs") else None,
            "note": None, "reason": said[0] if said else None, "more": max(0, len(said) - 1)}


SORTS = {"tripdate": "tripdate", "externalid": "externalid", "passenger": "passenger", "payer": "payer", "amount": "amount",
         "miles": "miles", "paid": "paid", "batchnumber": "batchnumber", "reason": "reason", "owing": "owing", "age": "age"}


@router.get("")
def queue(state: str = "ready", payer: str | None = None, q: str | None = None, sort: str = "tripdate", dir: str = "asc",
          page: int = 1, pagesize: int = 25, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """One queue of the four - ready, submitted, exceptions, paid - and the money across all of them."""
    acct = user["accountid"]
    if state not in ("ready", "submitted", "exceptions", "paid", "outstanding"):
        raise HTTPException(400, "Unknown state")
    live = _unbilled(conn, acct)
    ready = [_row(t) for t in live if not t["stops"] and not t["reasons"]]
    excepted = [_row(t) for t in live if t["stops"] or t["reasons"]]
    done = rows(conn, f"{TRIP} WHERE t.accountid = :a AND t.billingstatus IN ('billed', 'paid') AND t.deleted IS NULL", a=acct)
    submitted = [_row(t) for t in done if t["billingstatus"] == "billed"]
    paid = [_row(t) for t in done if t["billingstatus"] == "paid"]
    outstanding = [t for t in submitted + paid if t["owing"] > 0]
    aging = {"current": 0.0, "over30": 0.0, "over60": 0.0, "over90": 0.0}
    for t in outstanding:
        aging["over90" if t["age"] > 90 else "over60" if t["age"] > 60 else "over30" if t["age"] > 30 else "current"] += t["owing"]
    batches = rows(conn, """
        SELECT b.recordid AS batchid, b.number, p.name AS payer, COUNT(*) AS trips FROM billbatches b
        JOIN payers p ON p.recordid = b.payerid JOIN trips t ON t.billbatchid = b.recordid AND t.billingstatus = 'billed' AND t.deleted IS NULL
        WHERE b.accountid = :a GROUP BY b.recordid, b.number, p.name ORDER BY b.number
    """, a=acct)
    month = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    received = row(conn, "SELECT COALESCE(SUM(amount), 0) AS n FROM billpayments WHERE accountid = :a AND denied = 0 AND voidedon IS NULL AND recordedon >= :m", a=acct, m=month)["n"]
    items = {"ready": ready, "submitted": submitted, "exceptions": excepted, "paid": paid, "outstanding": outstanding}[state]
    payers = sorted({t["payer"] for t in ready + submitted + excepted + paid})
    if payer:
        items = [t for t in items if t["payer"] == payer]
    if q and q.strip():
        n = q.strip().upper()
        items = [t for t in items if n in t["externalid"].upper() or n in (t["passenger"] or "").upper()]
    key = SORTS.get(sort, "tripdate")
    items = sorted(items, key=lambda t: (t.get(key) is None, t.get(key) if t.get(key) is not None else 0, t["externalid"]),
                   reverse=str(dir).lower() == "desc")
    pagesize = max(1, min(pagesize, 200))
    return {"items": items[(max(1, page) - 1) * pagesize:max(1, page) * pagesize], "total": len(items), "page": page, "pagesize": pagesize, "payers": payers, "aging": aging, "batches": batches,
            "tiles": {"ready": {"count": len(ready), "amount": sum(t["amount"] for t in ready)},
                      "submitted": {"count": len(submitted), "amount": sum(t["amount"] for t in submitted)},
                      "exceptions": {"count": len(excepted)}, "paid": {"count": len(paid), "amount": float(received)},
                      "outstanding": {"count": len(outstanding), "amount": sum(t["owing"] for t in outstanding)}}}


def _one(conn: Connection, acct: str, tripid: str) -> dict:
    t = row(conn, f"{TRIP} WHERE t.recordid = :t AND t.accountid = :a AND t.deleted IS NULL", t=tripid, a=acct)
    if not t:
        raise HTTPException(404, "No such trip")
    return t


@router.get("/{tripid}")
def detail(tripid: str, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    t = _one(conn, acct, tripid)
    t.update(_read(conn, acct, t))
    if t["billingstatus"] in ("billed", "paid"):
        lines = rows(conn, "SELECT label, code, units, rate, amount FROM tripcharges WHERE tripid = :t AND accountid = :a AND voidedon IS NULL ORDER BY " + ORDER_LINES, t=tripid, a=acct)
        amount = sum((Decimal(str(x["amount"])) for x in lines), Decimal("0"))
    else:
        lines, amount = t["priced"]["lines"], t["priced"]["amount"]
    payments = rows(conn, "SELECT recordid, amount, writedown, denied, refund, note, recordedon, voidedon, voidreason FROM billpayments WHERE tripid = :t AND accountid = :a ORDER BY recordedon", t=tripid, a=acct)
    return {k: t[k] for k in ("recordid", "externalid", "tripdate", "passenger", "servicelevel", "payer", "billingstatus", "verifystate",
                              "billbatchid", "batchnumber", "billinvoiceid", "invoicenumber", "billtoemail", "emailedon", "emailerror", "legs", "stops", "reasons")} | {
        "paid": float(t["paid"] or 0), "writedown": float(t["writedown"] or 0) - float(t["refunded"] or 0), "refunded": float(t["refunded"] or 0),
        "owing": float(_owing(t)), "remindercount": t["remindercount"], "lastremindedon": t["lastremindedon"], "amount": float(amount),
        "payments": [{**p, "amount": float(p["amount"]), "writedown": float(p["writedown"])} for p in payments], "broker": bool(t["brokerid"]),
        "lines": [{"label": x["label"], "code": x["code"], "units": float(x["units"]), "rate": float(x["rate"]), "amount": float(x["amount"])} for x in lines]}


class BillIn(BaseModel):
    tripids: list[str]


@router.post("/bill")
def bill(body: BillIn, request: Request, tasks: BackgroundTasks, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """The ticked trips, each the way its payer is billed: a numbered batch per broker, a numbered
    invoice per private-pay trip, the charges written with the rates that produced them. All or
    nothing."""
    acct, now = user["accountid"], utcnow()
    chosen = [_one(conn, acct, i) for i in dict.fromkeys(body.tripids)]
    groups, private = {}, []
    for t in chosen:
        if t["billingstatus"] != "unbilled":
            raise HTTPException(409, f"{t['externalid']} is not ready to bill.")
        t.update(_read(conn, acct, t))
        if t["stops"] or t["reasons"]:
            raise HTTPException(409, f"{t['externalid']} is not ready to bill: {(t['stops'] + t['reasons'])[0]}")
        if t["brokerid"]:
            groups.setdefault(t["brokerid"], []).append(t)
        else:
            private.append(t)
    batches, invoices = [], []
    next_no = row(conn, "SELECT COALESCE(MAX(number), 1000) + 1 AS n FROM billbatches WHERE accountid = :a", a=acct)["n"]
    for payerid, trips in groups.items():
        total = sum((t["priced"]["amount"] for t in trips), Decimal("0"))
        bid = newid()
        run(conn, "INSERT INTO billbatches (recordid, accountid, number, payerid, trips, amount, createdon, createdby) "
                  "VALUES (:i, :a, :n, :p, :c, :m, :now, :by)", i=bid, a=acct, n=next_no, p=payerid, c=len(trips), m=total, now=now, by=user["recordid"])
        for t in trips:
            _charge(conn, acct, t, now, batchid=bid)
        batches.append({"batchid": bid, "number": next_no, "payer": trips[0]["payer"], "trips": len(trips), "amount": float(total)})
        log(conn, user, "bill-batch", "account", acct, {"batch": next_no, "trips": len(trips), "amount": str(total)}, ip=client_ip(request))
        next_no += 1
    next_inv = row(conn, "SELECT COALESCE(MAX(number), 1000) + 1 AS n FROM tripinvoices WHERE accountid = :a", a=acct)["n"]
    for t in private:
        who = row(conn, "SELECT address, city, state, zip, phone, email, billingname, billingemail, billingaddress FROM passengers WHERE accountid = :a AND name = :n AND deleted IS NULL ORDER BY added DESC LIMIT 1",
                  a=acct, n=t["passenger"])
        address = (who and (who["billingaddress"] or full(who))) or next((l["pickupplace"] for l in t["legs"] if l["pickupplace"]), None)
        email = who and (who["billingemail"] or who["email"]) or None
        iid, token = newid(), secrets.token_urlsafe(32)
        run(conn, """INSERT INTO tripinvoices (recordid, accountid, number, paytoken, tripid, billtoname, billtoaddress, billtophone, billtoemail, amount, issuedon, createdon, createdby)
                     VALUES (:i, :a, :n, :tok, :t, :name, :ad, :ph, :em, :m, :day, :now, :by)""",
            i=iid, a=acct, n=next_inv, tok=token, t=t["recordid"], name=((who and who["billingname"]) or t["passenger"] or "")[:160], ad=address, ph=who and who["phone"],
            em=email, m=t["priced"]["amount"],
            day=localnow(dispatch.zone(conn, acct)).date(), now=now, by=user["recordid"])
        _charge(conn, acct, t, now, invoiceid=iid)
        invoices.append({"invoiceid": iid, "number": next_inv, "passenger": t["passenger"], "amount": float(t["priced"]["amount"]), "email": email})
        if email:
            _queue_email(conn, tasks, acct, {"recordid": iid, "billtoemail": email, "number": next_inv, "amount": t["priced"]["amount"], "paytoken": token})
        log(conn, user, "invoice", "trip", t["recordid"], {"invoice": next_inv, "amount": str(t["priced"]["amount"])}, ip=client_ip(request))
        next_inv += 1
    saved(conn)
    return {"batches": batches, "invoices": invoices}


def _charge(conn: Connection, acct: str, t: dict, now, batchid: str | None = None, invoiceid: str | None = None) -> None:
    """The trip's charge lines written down with their rates; any from an earlier billing voided."""
    run(conn, "UPDATE tripcharges SET voidedon = :now WHERE tripid = :t AND accountid = :a AND voidedon IS NULL", now=now, t=t["recordid"], a=acct)
    for x in t["priced"]["lines"]:
        run(conn, """INSERT INTO tripcharges (recordid, accountid, tripid, legid, batchid, invoiceid, scheduleid, rateid, label, code, units, rate, amount, added)
                     VALUES (:i, :a, :t, :l, :b, :inv, :s, :r, :la, :c, :u, :ra, :am, :now)""",
            i=newid(), a=acct, t=t["recordid"], l=x["legid"], b=batchid, inv=invoiceid, s=t["priced"]["scheduleid"], r=x["rateid"], la=x["label"][:160],
            c=x["code"], u=x["units"], ra=x["rate"], am=x["amount"], now=now)
    run(conn, "UPDATE trips SET billingstatus = 'billed', billedamount = :m, billbatchid = :b, billinvoiceid = :inv, scheduleid = :s, updated = :now WHERE recordid = :t",
        m=t["priced"]["amount"], b=batchid, inv=invoiceid, s=t["priced"]["scheduleid"], now=now, t=t["recordid"])


def pay_link(accountnumber, token: str) -> str:
    return f"{settings.public_url.rstrip('/')}/pay/{accountnumber}/{token}"


def balance(conn: Connection, inv: dict) -> Decimal:
    """What is still owed on an invoice: its amount less what has been paid since it was issued."""
    paid = row(conn, "SELECT COALESCE(SUM(amount + writedown), 0) AS n FROM billpayments WHERE tripid = :t AND accountid = :a AND denied = 0 AND voidedon IS NULL AND recordedon >= :on",
               t=inv["tripid"], a=inv["accountid"], on=inv["createdon"])["n"]
    return _money(Decimal(str(inv["amount"])) - Decimal(str(paid)))


def _qr(url: str) -> str:
    import base64
    import io as bytesio

    import segno
    out = bytesio.BytesIO()
    segno.make(url, error="m").save(out, kind="png", scale=4, border=1)
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


def invoice_pdf(conn: Connection, acct: str, wanted: list[str]) -> bytes:
    """One or several invoices as a PDF, a page each. Charges are the invoice's own, voided or not."""
    company = row(conn, "SELECT name, accountnumber, address1, address2, city, state, zip, phone, billingemail FROM accounts WHERE recordid = :a", a=acct) or {}
    place = ", ".join(x for x in (company.get("city"), " ".join(y for y in (company.get("state"), company.get("zip")) if y)) if x)
    online = gateways.can_take_payment(conn, acct)
    short = f"{settings.public_url.rstrip('/').split('//')[-1]}/pay/{company.get('accountnumber')}"
    dollars = lambda v: f"${Decimal(str(v)):,.2f}"  # noqa: E731
    sheets = []
    for iid in wanted:
        inv = row(conn, "SELECT i.*, t.externalid, t.tripdate, t.servicelevel FROM tripinvoices i JOIN trips t ON t.recordid = i.tripid WHERE i.recordid = :i AND i.accountid = :a", i=iid, a=acct)
        if not inv:
            raise HTTPException(404, "No such invoice")
        lines = rows(conn, "SELECT label, units, rate, amount FROM tripcharges WHERE invoiceid = :i AND accountid = :a ORDER BY " + ORDER_LINES, i=iid, a=acct)
        owed = balance(conn, inv)
        took = row(conn, "SELECT COALESCE(SUM(amount), 0) AS paid, COALESCE(SUM(writedown), 0) AS down FROM billpayments WHERE tripid = :t AND denied = 0 AND voidedon IS NULL AND recordedon >= :on",
                   t=inv["tripid"], on=inv["createdon"])
        sender = " · ".join(x for x in (company.get("address1"), company.get("address2"), place, company.get("phone"), company.get("billingemail")) if x)
        if owed <= 0:
            pay = ""
        elif online:
            pay = view._section("Pay Online", f'<table style="width:100%"><tr><td style="width:110px;border:0"><img src="{_qr(pay_link(company.get("accountnumber"), inv["paytoken"]))}" style="width:96px;height:96px"></td>'
                                f'<td style="border:0">Scan the code with your phone, or go to <b>{view.escape(short)}</b> and enter invoice number <b>{inv["number"]}</b> and your billing ZIP code.</td></tr></table>')
        else:
            pay = view._section("How To Pay", f"<p>Call {view.escape(company.get('name') or '')}{' at ' + view.escape(company['phone']) if company.get('phone') else ''} to pay this invoice.</p>")
        sheets.append('<div class="sheet">' + view._letterhead(company.get("name"), f"Invoice {inv['number']}", f"Issued {inv['issuedon']:%m/%d/%Y}", "Due On Receipt")
                      + f'<p class="small">{view.escape(sender)}</p>'
                      + view._section("Bill To", "<p>" + "<br>".join(view.escape(x) for x in (inv["billtoname"], inv["billtoaddress"], inv["billtophone"]) if x) + "</p>")
                      + view._section("Trip", f"<p>{view.escape(inv['externalid'])} · {inv['tripdate']:%m/%d/%Y} · {view.escape((inv['servicelevel'] or '').title())}</p>")
                      + view._section("Charges", view._rows([("Charge", 58), ("Units", 12), ("Rate", 15), ("Amount", 15)],
                                                            [[x["label"], f"{Decimal(str(x['units'])).normalize():f}", dollars(x["rate"]), dollars(x["amount"])] for x in lines], least=0))
                      + view._section("Total", view._rows([("Invoice Total", 25), ("Paid", 25), ("Written Down", 25), ("Balance Due", 25)],
                                                          [[dollars(inv["amount"]), dollars(took["paid"]), dollars(took["down"]), dollars(owed)]], least=0))
                      + pay + "</div>")
    title = f"Invoice {inv['number']}" if len(wanted) == 1 else "Invoices"
    return view.to_pdf({"css": view.STYLE, "html": "".join(sheets), "title": title})


@router.get("/invoices/pdf")
def invoices_pdf(ids: str, request: Request, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    wanted = [i for i in ids.split(",") if i][:200]
    log(conn, user, "invoice-pdf", "account", acct, {"invoices": wanted}, ip=client_ip(request))
    saved(conn)
    return Response(invoice_pdf(conn, acct, wanted), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="invoices.pdf"'})


def _send_invoice(invoiceid: str, to: str, company: str, phone: str | None, number: int, amount: Decimal, link: str) -> None:
    """The amount and the link, nothing about the trip: email is not secure, and where somebody
    travels can say what they are treated for. The invoice itself is behind the link."""
    body = (emails.p(f"You have a new invoice from {emails.escape(company)}.")
            + emails.p(f"<strong>Invoice {number}: ${amount:,.2f}</strong>")
            + emails.button("View And Pay Invoice", link)
            + (emails.p(f"Questions? Call {emails.escape(company)} at {emails.escape(phone)}.", small=True) if phone else ""))
    html = emails.layout(preheader=f"Invoice {number} from {company}.", heading=f"Invoice {number}", body=body, footer_note=f"Sent for {emails.escape(company)}.")
    sent = mailer.send(to, f"Invoice {number} from {company}", html, f"Invoice {number} from {company}: ${amount:,.2f}. View and pay: {link}")
    with engine.begin() as conn:
        run(conn, "UPDATE tripinvoices SET emailedon = :on, emailerror = :e WHERE recordid = :i",
            on=utcnow() if sent else None, e=None if sent else "The email could not be sent.", i=invoiceid)


def _queue_email(conn: Connection, tasks: BackgroundTasks, acct: str, inv: dict) -> None:
    c = row(conn, "SELECT name, phone, accountnumber FROM accounts WHERE recordid = :a", a=acct)
    tasks.add_task(_send_invoice, inv["recordid"], inv["billtoemail"], c["name"], c["phone"], inv["number"], Decimal(str(inv["amount"])),
                   pay_link(c["accountnumber"], inv["paytoken"]))


@router.post("/invoices/{invoiceid}/email")
def resend(invoiceid: str, request: Request, tasks: BackgroundTasks, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    inv = row(conn, "SELECT * FROM tripinvoices WHERE recordid = :i AND accountid = :a", i=invoiceid, a=acct)
    if not inv:
        raise HTTPException(404, "No such invoice")
    if not inv["billtoemail"]:
        raise HTTPException(409, "There is no email address on this invoice.")
    _queue_email(conn, tasks, acct, inv)
    log(conn, user, "invoice-emailed", "trip", inv["tripid"], {"invoice": inv["number"]}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.get("/batches/{batchid}/export")
def export(batchid: str, request: Request, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """The batch as a spreadsheet to send through the broker's portal: one row a charge line."""
    acct = user["accountid"]
    batch = row(conn, "SELECT b.number, p.name AS payer FROM billbatches b JOIN payers p ON p.recordid = b.payerid WHERE b.recordid = :b AND b.accountid = :a", b=batchid, a=acct)
    if not batch:
        raise HTTPException(404, "No such batch")
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Batch", "Payer", "Trip", "Trip Date", "Passenger", "Member ID", "Service", "Leg", "Charge", "Code", "Units", "Rate", "Amount"])
    members: dict[str, dict] = {}
    for x in rows(conn, """
        SELECT c.tripid, c.label, c.code, c.units, c.rate, c.amount, t.externalid, t.tripdate, t.passenger, t.servicelevel, l.legnumber
        FROM tripcharges c JOIN trips t ON t.recordid = c.tripid LEFT JOIN triplegs l ON l.recordid = c.legid
        WHERE c.batchid = :b AND c.accountid = :a AND c.voidedon IS NULL ORDER BY t.tripdate, t.externalid, l.legnumber, c.label LIKE '%base fare%' DESC, c.label
    """, b=batchid, a=acct):
        member = members.setdefault(x["tripid"], phi.get(conn, acct, "trip", x["tripid"]) or {})
        w.writerow([batch["number"], batch["payer"], x["externalid"], x["tripdate"], x["passenger"], member.get("memberid") or "", x["servicelevel"],
                    x["legnumber"] or "", x["label"], x["code"] or "", x["units"], x["rate"], x["amount"]])
    log(conn, user, "bill-batch-export", "account", acct, {"batch": batch["number"]}, phi=True, ip=client_ip(request))
    saved(conn)
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="batch-{batch["number"]}.csv"'})


@router.post("/{tripid}/clear")
def clear(tripid: str, request: Request, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """A person has looked and it can be billed. What must be settled first still stops it."""
    acct = user["accountid"]
    t = _one(conn, acct, tripid)
    if t["billingstatus"] in ("billed", "paid"):
        raise HTTPException(409, "This trip has been billed already.")
    got = _read(conn, acct, t)
    if got["stops"]:
        raise HTTPException(409, got["stops"][0])
    run(conn, "UPDATE trips SET verifystate = 'verified', reviewedon = :now, reviewedby = :by, holdreason = NULL, billingstatus = 'unbilled', updated = :now "
              "WHERE recordid = :t AND accountid = :a", now=utcnow(), by=user["recordid"], t=tripid, a=acct)
    log(conn, user, "trip-cleared-to-bill", "trip", tripid, {"reasons": got["reasons"]}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class HoldIn(BaseModel):
    reason: str


@router.post("/{tripid}/hold")
def hold(tripid: str, body: HoldIn, request: Request, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    reason = " ".join(body.reason.split()).upper()[:600]
    if not reason:
        raise HTTPException(400, "Say why this trip is on hold")
    if _one(conn, acct, tripid)["billingstatus"] in ("billed", "paid"):
        raise HTTPException(409, "This trip has been billed already.")
    run(conn, "UPDATE trips SET verifystate = 'needscorrection', billingstatus = 'held', holdreason = :r, reviewedon = :now, reviewedby = :by, updated = :now "
              "WHERE recordid = :t AND accountid = :a", r=reason, now=utcnow(), by=user["recordid"], t=tripid, a=acct)
    log(conn, user, "trip-held", "trip", tripid, {"reason": reason}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class PaymentIn(BaseModel):
    amount: Decimal | None = None
    denied: bool = False
    writedown: Decimal | None = None   # this much of the balance given up, with why
    note: str | None = None


def _owing(t: dict) -> Decimal:
    return _money(Decimal(str(t["billedamount"] or 0)) - Decimal(str(t["paid"] or 0)) - Decimal(str(t["writedown"] or 0)))


def _note(v: str | None) -> str | None:
    return " ".join((v or "").split()).upper()[:600] or None


def _take(conn: Connection, user: dict, t: dict, body: PaymentIn, request: Request) -> None:
    """One thing that came back for a billed trip: paid; denied by a payer (never a passenger paying
    for themselves), to be fixed and billed again; or written down, closing it once nothing is owed."""
    acct, tripid, note = user["accountid"], t["recordid"], _note(body.note)
    owing, down = _owing(t), Decimal("0")
    if t["billingstatus"] not in ("billed", "paid") or owing <= 0:
        raise HTTPException(409, f"{t['externalid']} is not awaiting payment.")
    if body.denied:
        if t["billingstatus"] != "billed":
            raise HTTPException(409, f"{t['externalid']} is not awaiting payment.")
        if not t["brokerid"]:
            raise HTTPException(409, "A private-pay invoice cannot be denied. Write it down instead.")
        if not note:
            raise HTTPException(400, "Say why it was denied")
    elif body.writedown is not None:
        if not note:
            raise HTTPException(400, "Say why it is being written down")
        down = _money(body.writedown)
        if down <= 0 or down > owing:
            raise HTTPException(409, f"Write down between $0.01 and the balance of ${owing:,.2f}.")
    elif body.amount is None or body.amount < 0:
        raise HTTPException(400, "Give the amount paid")
    paid = _money(body.amount or 0) if not body.denied and body.writedown is None else Decimal("0")
    run(conn, "INSERT INTO billpayments (recordid, accountid, tripid, batchid, amount, writedown, denied, note, recordedon, recordedby) "
              "VALUES (:i, :a, :t, :b, :m, :w, :d, :n, :now, :by)", i=newid(), a=acct, t=tripid, b=t["billbatchid"], m=paid, w=down,
        d=int(body.denied), n=note, now=utcnow(), by=user["recordid"])
    if body.denied:
        run(conn, "UPDATE trips SET billingstatus = 'held', verifystate = 'needscorrection', holdreason = :r, updated = :now WHERE recordid = :t",
            r=f"DENIED BY THE PAYER: {note}"[:600], now=utcnow(), t=tripid)
    elif body.writedown is None or down >= owing:
        run(conn, "UPDATE trips SET billingstatus = 'paid', updated = :now WHERE recordid = :t", now=utcnow(), t=tripid)
    log(conn, user, "trip-payment", "trip", tripid, {"amount": str(paid), "writedown": str(down), "denied": body.denied, "note": note}, ip=client_ip(request))


@router.post("/{tripid}/payment")
def payment(tripid: str, body: PaymentIn, request: Request, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    _take(conn, user, _one(conn, user["accountid"], tripid), body, request)
    saved(conn)
    return {"ok": True}


class VoidIn(BaseModel):
    note: str | None = None


@router.post("/payments/{paymentid}/undo")
def undo(paymentid: str, body: VoidIn, request: Request, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """A payment, write-down, denial or refund entered in error. It stays on file, voided, with why,
    and the trip goes back to where that leaves it."""
    acct, note = user["accountid"], _note(body.note)
    if not note:
        raise HTTPException(400, "Say why this is being undone")
    p = row(conn, "SELECT * FROM billpayments WHERE recordid = :p AND accountid = :a AND voidedon IS NULL", p=paymentid, a=acct)
    if not p:
        raise HTTPException(404, "No such payment")
    run(conn, "UPDATE billpayments SET voidedon = :now, voidedby = :by, voidreason = :n WHERE recordid = :p",
        now=utcnow(), by=user["recordid"], n=note, p=paymentid)
    t = _one(conn, acct, p["tripid"])
    if p["denied"]:
        if t["billingstatus"] != "held":
            raise HTTPException(409, f"{t['externalid']} has moved on since it was denied.")
        run(conn, "UPDATE trips SET billingstatus = 'billed', verifystate = 'verified', holdreason = NULL, updated = :now WHERE recordid = :t", now=utcnow(), t=p["tripid"])
    elif t["billingstatus"] in ("billed", "paid"):
        run(conn, "UPDATE trips SET billingstatus = :s, updated = :now WHERE recordid = :t", s="paid" if _owing(t) <= 0 else "billed", now=utcnow(), t=p["tripid"])
    log(conn, user, "trip-payment-undone", "trip", p["tripid"], {"amount": str(p["amount"]), "note": note}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class RefundIn(BaseModel):
    amount: Decimal
    note: str | None = None


@router.post("/{tripid}/refund")
def refund(tripid: str, body: RefundIn, request: Request, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Money given back, recorded here once it has been returned through the processor. Nothing more
    is owed for it: the trip stays closed."""
    acct, note, amount = user["accountid"], _note(body.note), _money(body.amount)
    t = _one(conn, acct, tripid)
    if not note:
        raise HTTPException(400, "Say why this is being refunded")
    if amount <= 0 or amount > Decimal(str(t["paid"] or 0)):
        raise HTTPException(409, f"Refund between $0.01 and the ${Decimal(str(t['paid'] or 0)):,.2f} paid.")
    run(conn, "INSERT INTO billpayments (recordid, accountid, tripid, batchid, amount, writedown, refund, note, recordedon, recordedby) "
              "VALUES (:i, :a, :t, :b, :m, :w, 1, :n, :now, :by)", i=newid(), a=acct, t=tripid, b=t["billbatchid"], m=-amount, w=amount, n=note, now=utcnow(), by=user["recordid"])
    log(conn, user, "trip-refund", "trip", tripid, {"amount": str(amount), "note": note}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class MilesIn(BaseModel):
    miles: Decimal
    reason: str | None = None


@router.post("/legs/{legid}/miles")
def correct_miles(legid: str, body: MilesIn, request: Request, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """The office's figure for a leg's miles, with why. Used for pricing; the GPS trail and the
    driver's figure stay as they were."""
    acct, reason = user["accountid"], _note(body.reason)
    leg = row(conn, "SELECT l.tripid, l.miles, t.billingstatus FROM triplegs l JOIN trips t ON t.recordid = l.tripid WHERE l.recordid = :l AND l.accountid = :a", l=legid, a=acct)
    if not leg:
        raise HTTPException(404, "No such leg")
    if leg["billingstatus"] in ("billed", "paid"):
        raise HTTPException(409, "This trip has been billed already.")
    if not reason:
        raise HTTPException(400, "Say why the miles are being corrected")
    dispatch.plausible_miles(round(float(body.miles), 1))
    run(conn, "UPDATE triplegs SET officemiles = :m, officemilesreason = :r, officemilesby = :by, officemileson = :now WHERE recordid = :l",
        m=body.miles, r=reason, by=user["recordid"], now=utcnow(), l=legid)
    log(conn, user, "leg-miles-corrected", "trip", leg["tripid"], {"leg": legid, "miles": str(body.miles), "reason": reason}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.get("/batches/{batchid}")
def batch(batchid: str, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """A batch's trips still owed on, for posting what the broker paid."""
    acct = user["accountid"]
    b = row(conn, "SELECT b.number, b.amount, p.name AS payer FROM billbatches b JOIN payers p ON p.recordid = b.payerid WHERE b.recordid = :b AND b.accountid = :a", b=batchid, a=acct)
    if not b:
        raise HTTPException(404, "No such batch")
    trips = rows(conn, f"{TRIP} WHERE t.accountid = :a AND t.billbatchid = :b AND t.billingstatus = 'billed' AND t.deleted IS NULL ORDER BY t.tripdate, t.externalid", a=acct, b=batchid)
    return {**b, "trips": [{"recordid": t["recordid"], "externalid": t["externalid"], "tripdate": t["tripdate"], "passenger": t["passenger"], "owing": float(_owing(t))} for t in trips]}


class BatchLine(BaseModel):
    tripid: str
    amount: Decimal | None = None
    denied: bool = False
    note: str | None = None


class BatchIn(BaseModel):
    lines: list[BatchLine]


@router.post("/batches/{batchid}/payment")
def batch_payment(batchid: str, body: BatchIn, request: Request, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """What the broker paid against a batch, trip by trip. All of it, or none of it."""
    acct = user["accountid"]
    for line in body.lines:
        t = _one(conn, acct, line.tripid)
        if t["billbatchid"] != batchid:
            raise HTTPException(409, f"{t['externalid']} is not in this batch.")
        _take(conn, user, t, PaymentIn(amount=line.amount, denied=line.denied, note=line.note), request)
    saved(conn)
    return {"posted": len(body.lines)}


# ------------------------------------------------------------------------------------------------
# Reminders: an unpaid private-pay invoice is emailed again, at these days after it was issued.
# ------------------------------------------------------------------------------------------------
REMINDERS = (14, 30)


def send_reminders(conn: Connection) -> int:
    """Run hourly. A reminder that could not be sent is tried again next time, not counted."""
    now, sent = utcnow(), 0
    for inv in rows(conn, """
        SELECT i.*, a.name AS company, a.phone AS companyphone, a.accountnumber FROM tripinvoices i
        JOIN trips t ON t.recordid = i.tripid AND t.billinvoiceid = i.recordid AND t.billingstatus = 'billed' AND t.deleted IS NULL
        JOIN accounts a ON a.recordid = i.accountid
        WHERE i.billtoemail IS NOT NULL AND i.remindercount < :most
    """, most=len(REMINDERS)):
        if (now - inv["createdon"]).days < REMINDERS[inv["remindercount"]] or balance(conn, inv) <= 0:
            continue
        owed = balance(conn, inv)
        link = pay_link(inv["accountnumber"], inv["paytoken"])
        body = (emails.p(f"Invoice {inv['number']} from {emails.escape(inv['company'])} is still unpaid.")
                + emails.p(f"<strong>Balance due: ${owed:,.2f}</strong>") + emails.button("View And Pay Invoice", link)
                + (emails.p(f"Questions? Call {emails.escape(inv['company'])} at {emails.escape(inv['companyphone'])}.", small=True) if inv["companyphone"] else ""))
        html = emails.layout(preheader=f"Invoice {inv['number']} is still unpaid.", heading=f"Invoice {inv['number']}", body=body, footer_note=f"Sent for {emails.escape(inv['company'])}.")
        if mailer.send(inv["billtoemail"], f"Reminder: invoice {inv['number']} from {inv['company']}", html,
                       f"Invoice {inv['number']} from {inv['company']} is still unpaid. Balance due: ${owed:,.2f}. View and pay: {link}"):
            run(conn, "UPDATE tripinvoices SET remindercount = remindercount + 1, lastremindedon = :now WHERE recordid = :i", now=now, i=inv["recordid"])
            sent += 1
    return sent
