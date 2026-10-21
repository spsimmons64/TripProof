"""What a company charges, and what a payer contracts to pay.

Two different facts, held the same way: a schedule belongs to a payer - private pay, or a
named broker - and carries dated rate components. Base fares, mileage, waiting time and
surcharges are rows rather than columns, because a schema with `baserate` and `permile` on it
cannot hold the fourth thing a contract invents, and contracts invent things.

Nothing here prices a trip yet. This is the schedule; the calculator that turns a completed
trip into a charge comes next, and when it does it must record WHICH rate produced the
number - a trip carried last March stays priced at last March's rates for ever, except where
somebody deliberately re-prices it.
"""

from datetime import date

from decimal import Decimal

from sqlalchemy.engine import Connection

from app import payerlines
from app.db import newid, row, rows, run, utcnow
from app.dispatch import SERVICE

# The three a transport company bills differently. A Medicare Advantage plan, a commercial
# insurer, a workers' compensation carrier and a facility on a flat contract are all one
# thing from here: an organisation with contracted rates. What separates them lives on the
# payer's own record and in how it is billed, not in a type used to choose a fee schedule.
CATEGORIES = {
    "broker": "Transportation Broker",
    "commercial": "Commercial Payer",
    "medicaid": "Medicaid",
    # A facility, a care home, an employer - somebody with an agreed price rather than a
    # metered one. Keyed `flatcontract` and not `flat`, which is already a billing method:
    # the same word in two fields on one screen is how somebody reads one as the other.
    "flatcontract": "Flat Contract",
}

# The same three said of a group, for "All Transportation Brokers". Held beside the singular
# rather than pluralised by the screen: "Medicaid" becomes "Medicaid Payers", not "Medicaids",
# and a rule that knows that is a rule with an exception list in it.
CATEGORY_PLURAL = {
    "broker": "Transportation Brokers",
    "commercial": "Commercial Payers",
    "medicaid": "Medicaid Payers",
    "flatcontract": "Flat Contracts",
}

RATE_TYPES = {
    "base": "Base fare",
    "mileage": "Mileage",
    "waiting": "Waiting time",
    "flat": "Flat trip rate",
    "surcharge": "Surcharge",
    "noshow": "No-show",
}

UNITS = {
    "trip": "per trip",
    "leg": "per leg",
    "mile": "per mile",
    "minute": "per minute",
    "block15": "per 15 minutes",
    "hour": "per hour",
}

# Read from the one definition in `dispatch`, never copied. What a company can price and
# what it can dispatch are the same list of services, and the day they stop being the same
# list is the day somebody prices a trip nobody can book.
SERVICES = {k: v["label"] for k, v in SERVICE.items()}

# How a schedule is billed, worked out from who it applies to. Not asked and not stored.
BILLED_AS = {
    None: "direct",            # the passenger
    "broker": "invoice",
    "medicaid": "claim",
    "commercial": "claim",
    "flatcontract": "flat",
}

BILLING = {
    "invoice": "Broker invoice",
    "claim": "Medicaid claim",
    "flat": "Flat contract",
    "direct": "Billed to the passenger",
}

ROUNDING = {"none": "Exact", "tenth": "Tenth of a mile", "whole": "Whole miles"}


def billed_as(schedule: dict) -> str:
    """How this schedule is billed. One answer, every time, from who it applies to."""
    if schedule.get("privatepay"):
        return BILLED_AS[None]
    kind = schedule.get("payercategory")
    return BILLED_AS.get(kind, "invoice")


def schedules(conn: Connection, accountid: str) -> list[dict]:
    """Every schedule this company holds, newest contract first."""
    out = rows(conn, """
        SELECT s.recordid, s.name, s.contractref,
               s.effectivefrom,
               s.effectiveto, s.note, s.active, s.updated,
               -- How many payers, and state lines, are paid under it.
               (SELECT COUNT(*) FROM accountpayers ap
                 WHERE ap.scheduleid = s.recordid) + (SELECT COUNT(*) FROM companycontracts c
                 WHERE c.scheduleid = s.recordid) AS payercount,
               -- Its payer type, which is also how it is billed.
               s.privatepay, s.payerkinds AS payercategory,
               (SELECT COUNT(*) FROM payerrates r WHERE r.scheduleid = s.recordid) AS rates
        FROM payerschedules s
        WHERE s.accountid = :a
        ORDER BY s.active DESC, s.effectivefrom DESC, s.name
    """, a=accountid)
    for r in out:
        r["billingmethod"] = billed_as(r)
    return out


def schedule(conn: Connection, accountid: str, scheduleid: str) -> dict | None:
    got = row(conn, """
        SELECT s.* FROM payerschedules s WHERE s.recordid = :i AND s.accountid = :a
    """, i=scheduleid, a=accountid)
    if not got:
        return None
    got["payercategory"] = got["payerkinds"]
    got["billingmethod"] = billed_as(got)
    got["rates"] = rows(conn, """
        SELECT * FROM payerrates WHERE scheduleid = :i ORDER BY sortorder, ratetype
    """, i=scheduleid)
    return got


def in_force(conn: Connection, accountid: str, *, payerid: str | None = None,
             on=None, state: str | None = None) -> dict | None:
    """The schedule that governs a trip on a given day.

    Read off the payer's line for the state the trip is picked up in - no payer is the passenger,
    whose line is private pay. Where the pickup does not say, the company's home state stands in.
    The schedule is the line's own where that state is paid differently, otherwise the payer's.
    Where that schedule replaces another and has not started yet, the one it replaces prices the
    day.
    """
    state = (state or (row(conn, "SELECT state FROM accounts WHERE recordid = :a",
                           a=accountid) or {}).get("state") or "").upper()[:2] or None
    line = row(conn, f"""
        SELECT c.scheduleid FROM companycontracts c
        WHERE c.accountid = :a AND c.payerid <=> :p AND c.status = 'active'
          AND {payerlines.live("c")}
          AND (c.state IS NULL OR c.state = :st)
          AND (c.effectivefrom IS NULL OR c.effectivefrom <= :on)
          AND (c.effectiveto IS NULL OR c.effectiveto >= :on)
        ORDER BY c.state IS NOT NULL DESC LIMIT 1
    """, a=accountid, p=payerid, st=state, on=on)
    if not line:
        return None                 # the payer is not carried for in that state
    sid = line["scheduleid"] or (row(conn, """
        SELECT scheduleid FROM accountpayers WHERE accountid = :a AND payerid = :p
    """, a=accountid, p=payerid or PRIVATE) or {}).get("scheduleid")
    seen = set()
    while sid and sid not in seen:
        seen.add(sid)
        card = row(conn, "SELECT s.* FROM payerschedules s WHERE s.recordid = :i AND s.accountid = :a",
                   i=sid, a=accountid)
        if not card or not card["active"]:
            return None
        if card["effectivefrom"] <= on and (card["effectiveto"] is None or card["effectiveto"] >= on):
            return card
        # Not started yet: the schedule it replaces still prices the day.
        sid = card["supersedes"] if card["effectivefrom"] > on else None
    return None


def quote(conn: Connection, accountid: str, *, payerid: str | None, servicelevel: str,
           on, legs: int = 1, miles=None, state: str | None = None) -> dict:
    """What this trip comes to under the schedule in force for its payer.

    Honest about what it does not know. At booking nobody has driven anywhere, so mileage cannot
    be priced and is left out of the figure with the omission stated - a number presented as the
    whole of a fare, which later grows by thirty dollars of mileage, is worse than no number.

    A flat rate wins outright where one is set for the service: that is what a flat rate means.
    """
    card = in_force(conn, accountid, payerid=payerid, on=on, state=state)
    if not card:
        return {"scheduleid": None, "schedulename": None, "amount": None, "lines": [],
                "complete": False,
                "why": "No fee schedule is set for this payer, or it is not carried for in "
                       "that state, on that date - so there is no price."}
    lines = rows(conn, "SELECT * FROM payerrates WHERE scheduleid = :i ORDER BY sortorder, ratetype",
                 i=card["recordid"])
    # A line for this service, or one that names no service and therefore covers them all.
    mine = [r for r in lines if (r["servicelevel"] or "") in ("", servicelevel)]
    said, total = [], Decimal("0")

    flat = next((r for r in mine if r["ratetype"] == "flat"), None)
    if flat:
        each = Decimal(str(flat["amount"] or 0))
        count = legs if (flat["unit"] == "leg") else 1
        total = each * count
        said.append({"name": flat["name"], "amount": float(each * count)})
        return {"scheduleid": card["recordid"], "schedulename": card["name"],
                "amount": float(total), "lines": said, "complete": True,
                "why": "A flat rate covers the whole trip."}

    base = next((r for r in mine if r["ratetype"] == "base"), None)
    if base:
        each = Decimal(str(base["amount"] or 0))
        count = legs if (base["unit"] == "leg") else 1
        total += each * count
        said.append({"name": base["name"], "amount": float(each * count)})

    mileage = next((r for r in mine if r["ratetype"] == "mileage"), None)
    complete = True
    if mileage:
        if miles is None:
            complete = False
        else:
            free = Decimal(str(mileage["includedunits"] or 0))
            chargeable = max(Decimal("0"), Decimal(str(miles)) - free)
            amount = chargeable * Decimal(str(mileage["amount"] or 0))
            total += amount
            said.append({"name": mileage["name"], "amount": float(amount)})
    why = ("The base fare. Mileage is added when the trip has been driven."
           if mileage and miles is None else
           "Base fare and mileage." if mileage else
           "The base fare." if base else
           "This schedule prices nothing for that service level.")
    return {"scheduleid": card["recordid"], "schedulename": card["name"],
            "amount": float(total) if said else None, "lines": said,
            "complete": complete and bool(said), "why": why}


FOREVER = "9999-12-31"
# Private pay has no payer row; its fee schedule is kept under this key.
PRIVATE = "privatepay"


def kind_of(schedule: dict) -> str | None:
    """A schedule's payer type: 'private', or one payer category."""
    return "private" if schedule.get("privatepay") else (schedule.get("payerkinds") or None)


def set_payer_schedule(conn: Connection, accountid: str, payerid: str, kind: str,
                       scheduleid: str | None, userid: str | None) -> None:
    """The fee schedule this company is paid under by a payer - one of its own type, and active."""
    if scheduleid:
        held = row(conn, "SELECT privatepay, payerkinds, active FROM payerschedules "
                         "WHERE recordid = :i AND accountid = :a", i=scheduleid, a=accountid)
        if not held or not held["active"]:
            raise ValueError("No such active fee schedule")
        if kind_of(held) != kind:
            raise ValueError("That fee schedule is for a different payer type")
    run(conn, """
        INSERT INTO accountpayers (accountid, payerid, scheduleid, updated, updatedby)
        VALUES (:a, :p, :s, :now, :u)
        ON DUPLICATE KEY UPDATE scheduleid = :s, updated = :now, updatedby = :u
    """, a=accountid, p=payerid, s=scheduleid or None, now=utcnow(), u=userid)


def save_schedule(conn: Connection, accountid: str, userid: str, body: dict,
                  scheduleid: str | None = None) -> str:
    fields = dict(
        name=body["name"].strip()[:120],
        # Its payer type: private pay, or one kind of payer. A payer is offered only schedules
        # of its own type; which payer pays under it is said on the payer.
        privatepay=1 if body.get("payertype") == "private" else 0,
        payerkinds=body.get("payertype") if body.get("payertype") in CATEGORIES else None,
        supersedes=body.get("supersedes") or None,
        contractref=(body.get("contractref") or "").strip()[:64] or None,
        # The screen no longer asks when a schedule starts - it starts when it is written.
        # The column stays: superseding a contract on a date is a real thing a carrier does,
        # and the day it is needed the dates already on file are the ones that matter.
        effectivefrom=body.get("effectivefrom") or date.today(),
        effectiveto=body.get("effectiveto") or None,
        note=(body.get("note") or "").strip()[:512] or None,
        active=1 if body.get("active", True) else 0,
    )
    if scheduleid:
        run(conn, """
            UPDATE payerschedules SET name=:name, privatepay=:privatepay, payerkinds=:payerkinds,
                   contractref=:contractref, effectivefrom=:effectivefrom,
                   effectiveto=:effectiveto, note=:note,
                   active=:active, updated=:now
            WHERE recordid = :i AND accountid = :a
        """, i=scheduleid, a=accountid, now=utcnow(),
            **{k: v for k, v in fields.items() if k != "supersedes"})
        return scheduleid
    scheduleid = newid()
    run(conn, """
        INSERT INTO payerschedules (recordid, accountid, name, privatepay, payerkinds, supersedes,
                                    contractref, effectivefrom, effectiveto,
                                    note, active, addedby)
        VALUES (:i, :a, :name, :privatepay, :payerkinds, :supersedes, :contractref, :effectivefrom,
                :effectiveto, :note, :active, :by)
    """, i=scheduleid, a=accountid, by=userid, **fields)
    # A replacement takes over the lines of the schedule it replaces. Until it starts, pricing
    # follows `supersedes` back to the old one, so no day is left without a price.
    if fields["supersedes"]:
        for table in ("companycontracts", "accountpayers"):
            run(conn, f"UPDATE {table} SET scheduleid = :n WHERE scheduleid = :o "
                      "AND accountid = :a", n=scheduleid, o=fields["supersedes"], a=accountid)
    return scheduleid


def save_rates(conn: Connection, accountid: str, scheduleid: str, lines: list[dict]) -> int:
    """Replace a schedule's rate lines with the ones given.

    Replaced wholesale rather than patched line by line: the screen edits a table and sends
    the table back, and reconciling which row is which would be guesswork over rows that
    have no natural key.
    """
    run(conn, "DELETE FROM payerrates WHERE scheduleid = :i", i=scheduleid)
    kept = 0
    for order, line in enumerate(lines):
        if line.get("ratetype") not in RATE_TYPES:
            continue
        run(conn, """
            INSERT INTO payerrates (recordid, accountid, scheduleid, ratetype, name,
                                    servicelevel, unit, amount, includedunits, minimumunits,
                                    rounding, proceduracode, modifier, authrequired, note,
                                    loadedonly, sortorder)
            VALUES (:i, :a, :s, :t, :nm, :svc, :u, :amt, :inc, :min, :rnd, :code, :mod, :auth,
                    :note, :loaded, :o)
        """, i=newid(), a=accountid, s=scheduleid, t=line["ratetype"],
            nm=(line.get("name") or "").strip()[:80] or None,
            svc=line.get("servicelevel") or None, u=line.get("unit", "trip"),
            # Only mileage has an opinion about which miles. Elsewhere it is left null rather
            # than 0, because 0 would read as a decision to bill total miles.
            loaded=(1 if line.get("loadedonly") else 0)
                   if line["ratetype"] == "mileage" else None,
            amt=line.get("amount") or 0, inc=line.get("includedunits"),
            min=line.get("minimumunits"), rnd=line.get("rounding") or None,
            code=(line.get("proceduracode") or "").strip()[:16] or None,
            mod=(line.get("modifier") or "").strip()[:8] or None,
            auth=1 if line.get("authrequired") else 0,
            note=(line.get("note") or "").strip()[:255] or None, o=order)
        kept += 1
    return kept


def set_active(conn: Connection, accountid: str, scheduleid: str, active: bool) -> bool:
    """Whether this schedule counts at all, on any day.

    Not the same question as its dates. The dates say which days a schedule governs; this
    says whether it is to be read at all - the "entered wrong, pretend it never applied"
    case. Retiring one that has already priced trips should be refused once charges exist,
    because it would orphan the explanation of a number somebody was billed.
    """
    return bool(run(conn, """
        UPDATE payerschedules SET active = :on, updated = :now
        WHERE recordid = :i AND accountid = :a
    """, on=1 if active else 0, now=utcnow(), i=scheduleid, a=accountid).rowcount)


def remove(conn: Connection, accountid: str, scheduleid: str) -> bool:
    """Take a schedule out of use. Deactivated, never deleted - see set_active."""
    return set_active(conn, accountid, scheduleid, False)


# -------------------------------------------------------------------------------------------
# Payers - who a company bills.
#
# A company keeps its own list. The shared rows (accountid NULL) are the brokers TripProof
# publishes compliance rules for: a trip carried for one of those is checked against that
# broker's requirements, which only works while everybody is pointing at the same row. So
# they are offered to every company and editable by none of them.
# -------------------------------------------------------------------------------------------

# Where a payer is. The same names the company profile uses, so one address is read the
# same way wherever it appears.
ADDRESS = ("address1", "address2", "city", "state", "zip", "phone", "fax", "contactname",
           "contactemail")
# The part of it that is the company's own rather than the payer's.
CONTACT = ("contactname", "contactemail")


def payers(conn: Connection, accountid: str) -> list[dict]:
    """Everyone this company can bill: the shared catalogue, and its own."""
    return rows(conn, f"""
        SELECT p.recordid, p.code, p.name, p.category, p.payerid, p.website, p.notes,
               -- Whether THIS company works with it: its own say about a shared payer first.
               COALESCE(ap.active, p.active) AS active, ap.active IS NOT NULL AS decided,
               ap.scheduleid,
               p.accountid IS NULL AS shared,
               -- A company's own broker that is also on the master list reads its address and
               -- contact from the master, so there is one copy of where a broker is.
               m.recordid IS NOT NULL AS mastered,
               {", ".join(f"CASE WHEN m.recordid IS NULL THEN p.{c} ELSE m.{c} END AS {c}"
                          for c in ADDRESS if c not in CONTACT)},
               -- Who the company deals with there is its own, at a shared payer as at its own.
               {", ".join(f"CASE WHEN p.accountid IS NULL THEN COALESCE(ap.{c}, p.{c}) "
                          f"ELSE p.{c} END AS {c}" for c in CONTACT)},
               (SELECT COUNT(*) FROM payerdocuments d
                 WHERE d.payerid = p.recordid AND d.accountid = :a) AS documents,
               -- The fee schedules its lines name.
               (SELECT COUNT(DISTINCT c.scheduleid) FROM companycontracts c
                 WHERE c.accountid = :a AND c.payerid = p.recordid
                   AND c.scheduleid IS NOT NULL) AS schedules
        FROM payers p
        LEFT JOIN accountpayers ap ON ap.payerid = p.recordid AND ap.accountid = :a
        LEFT JOIN payers m ON m.recordid = (
            SELECT m2.recordid FROM payers m2
            WHERE p.accountid IS NOT NULL AND p.category = 'broker'
              AND m2.accountid IS NULL AND m2.category = 'broker' AND UPPER(m2.name) = UPPER(p.name)
            LIMIT 1)
        WHERE p.accountid IS NULL OR p.accountid = :a
        ORDER BY p.accountid IS NULL DESC, p.category, p.name
    """, a=accountid)


def _code_for(conn: Connection, accountid: str | None, name: str, code: str | None) -> str:
    """A short handle, made from the name when nobody supplies one.

    Unique within the company rather than across the product: another company already having
    a payer called ST JOSEPHS is not this company's problem.
    """
    base = "".join(ch for ch in (code or name).upper() if ch.isalnum())[:28] or "PAYER"
    taken = {r["code"] for r in rows(conn, """
        SELECT code FROM payers WHERE accountid IS NULL OR accountid = :a
    """, a=accountid)}
    if base not in taken:
        return base
    for n in range(2, 100):
        if f"{base}{n}"[:32] not in taken:
            return f"{base}{n}"[:32]
    return newid()[:32]


def save_payer(conn: Connection, accountid: str | None, body: dict,
               payerrecordid: str | None = None) -> str:
    """Write a payer.

    `accountid` None is the shared catalogue, which only platform staff reach. One function
    for both, because a payer's address is a payer's address: two writers would be two places
    to add a field to, and the one that got missed would quietly stop saving it.
    """
    fields = dict(
        name=body["name"].strip()[:128],
        category=body.get("category") if body.get("category") in CATEGORIES else "commercial",
        payerid=(body.get("payerid") or "").strip()[:24] or None,
        website=(body.get("website") or "").strip()[:255] or None,
        notes=(body.get("notes") or "").strip() or None,
        active=1 if body.get("active", True) else 0,
        **{c: (body.get(c) or "").strip()[:128] or None for c in ADDRESS},
    )
    # Two characters, upper case, like every other state in the product.
    if fields["state"]:
        fields["state"] = fields["state"].upper()[:2]
    if payerrecordid:
        run(conn, """
            UPDATE payers SET name=:name, category=:category, payerid=:payerid,
                   website=:website, notes=:notes, active=:active, updated=:now,
                   {address}
            WHERE recordid = :i AND {owner}
        """.format(address=", ".join(f"{c}=:{c}" for c in ADDRESS),
                   owner="accountid IS NULL" if accountid is None else "accountid = :a"),
            i=payerrecordid, a=accountid, now=utcnow(), **fields)
        return payerrecordid
    payerrecordid = newid()
    run(conn, """
        INSERT INTO payers (recordid, accountid, code, name, category, payerid, website,
                            notes, active, address1, address2, city, state, zip, phone,
                            fax, contactname, contactemail)
        VALUES (:i, :a, :code, :name, :category, :payerid, :website, :notes, :active,
                :address1, :address2, :city, :state, :zip, :phone, :fax, :contactname,
                :contactemail)
    """, i=payerrecordid, a=accountid,
        code=_code_for(conn, accountid, fields["name"], body.get("code")), **fields)
    return payerrecordid


def payer_in_use(conn: Connection, accountid: str, payerrecordid: str) -> int:
    """Schedules, trips and payer lines that would be orphaned by removing this payer."""
    return row(conn, """
        SELECT (SELECT COUNT(*) FROM trips WHERE accountid = :a AND brokerid = :i)
             + (SELECT COUNT(*) FROM companycontracts WHERE accountid = :a AND payerid = :i) AS n
    """, a=accountid, i=payerrecordid)["n"]


def remove_payer(conn: Connection, accountid: str, payerrecordid: str) -> bool:
    """Only this company's own, and only while nothing points at it."""
    return bool(run(conn, """
        DELETE FROM payers WHERE recordid = :i AND accountid = :a
    """, i=payerrecordid, a=accountid).rowcount)


def documents(conn: Connection, accountid: str, payerrecordid: str) -> list[dict]:
    """What this company holds on file for this payer, newest first."""
    return rows(conn, """
        SELECT pd.recordid, pd.title, pd.effectivefrom, pd.effectiveto, pd.note, pd.added,
               pd.documentid, d.filename, d.bytes, d.mimetype
        FROM payerdocuments pd
        JOIN documents d ON d.recordid = pd.documentid AND d.deleted IS NULL
        WHERE pd.accountid = :a AND pd.payerid = :p
        ORDER BY pd.effectivefrom IS NULL, pd.effectivefrom DESC, pd.added DESC
    """, a=accountid, p=payerrecordid)


def add_document(conn: Connection, accountid: str, userid: str, payerrecordid: str,
                 documentid: str, body: dict) -> str:
    recordid = newid()
    run(conn, """
        INSERT INTO payerdocuments (recordid, accountid, payerid, documentid, title,
                                    effectivefrom, effectiveto, note, addedby)
        VALUES (:i, :a, :p, :d, :t, :from, :to, :n, :by)
    """, i=recordid, a=accountid, p=payerrecordid, d=documentid,
        t=(body.get("title") or "Document").strip()[:120],
        **{"from": body.get("effectivefrom") or None, "to": body.get("effectiveto") or None},
        n=(body.get("note") or "").strip()[:512] or None, by=userid)
    return recordid


def remove_document(conn: Connection, accountid: str, recordid: str) -> bool:
    """Unfile it from the payer.

    The document itself is left in place: the same bytes may be filed against something else,
    and storage deduplicates by hash, so deleting it here could pull a file out from under
    another record.
    """
    return bool(run(conn, """
        DELETE FROM payerdocuments WHERE recordid = :i AND accountid = :a
    """, i=recordid, a=accountid).rowcount)
