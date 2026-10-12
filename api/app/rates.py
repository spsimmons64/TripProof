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

from sqlalchemy.engine import Connection

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
    kind = (schedule.get("payerkinds") or "").split(",")[0] or schedule.get("payercategory")
    return BILLED_AS.get(kind, "invoice")


def schedules(conn: Connection, accountid: str) -> list[dict]:
    """Every schedule this company holds, newest contract first."""
    out = rows(conn, """
        SELECT s.recordid, s.name, s.privatepay, s.payerkinds, s.contractref,
               s.effectivefrom,
               s.effectiveto, s.note, s.active, s.updated,
               -- Who it prices, read as names. A schedule covering four facilities should
               -- say so in the list without the list opening four things.
               (SELECT GROUP_CONCAT(p.name ORDER BY p.name SEPARATOR ', ')
                  FROM schedulepayers sp JOIN payers p ON p.recordid = sp.payerid
                 WHERE sp.scheduleid = s.recordid) AS payernames,
               (SELECT COUNT(*) FROM schedulepayers sp
                 WHERE sp.scheduleid = s.recordid) AS payercount,
               -- The payers on a schedule are all of one type, which is what the screen
               -- offers; this is that type, for working out how it is billed.
               (SELECT MIN(p.category) FROM schedulepayers sp
                  JOIN payers p ON p.recordid = sp.payerid
                 WHERE sp.scheduleid = s.recordid) AS payercategory,
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
    got["payercategory"] = row(conn, """
        SELECT MIN(p.category) AS category FROM schedulepayers sp
        JOIN payers p ON p.recordid = sp.payerid WHERE sp.scheduleid = :i
    """, i=scheduleid)["category"]
    got["billingmethod"] = billed_as(got)
    got["payerids"] = [r["payerid"] for r in rows(conn, """
        SELECT sp.payerid FROM schedulepayers sp
        JOIN payers p ON p.recordid = sp.payerid
        WHERE sp.scheduleid = :i ORDER BY p.name
    """, i=scheduleid)]
    got["rates"] = rows(conn, """
        SELECT * FROM payerrates WHERE scheduleid = :i ORDER BY sortorder, ratetype
    """, i=scheduleid)
    return got


def in_force(conn: Connection, accountid: str, *, payerid: str | None = None,
             on=None) -> dict | None:
    """The schedule that governs a trip on a given day.

    Keyed on the payer, and on nothing else. No payer means the passenger is paying, which is
    why private pay needs no special case: it is the schedule with nobody else on it.

    One answer, not a list: two schedules covering the same payer on the same day is a
    contradiction, and the most recently effective one wins rather than the question being
    left open at the moment somebody needs a price.
    """
    if payerid is None:
        return row(conn, """
            SELECT s.* FROM payerschedules s
            WHERE s.accountid = :a AND s.active = 1 AND s.privatepay = 1
              AND s.effectivefrom <= :on
              AND (s.effectiveto IS NULL OR s.effectiveto >= :on)
            ORDER BY s.effectivefrom DESC LIMIT 1
        """, a=accountid, on=on)
    # Named first, then the payer's kind. One query, ranked, so the override and the default
    # are compared on the same dates rather than fetched separately and reconciled.
    return row(conn, """
        SELECT s.*,
               EXISTS (SELECT 1 FROM schedulepayers sp
                        WHERE sp.scheduleid = s.recordid AND sp.payerid = p.recordid)
                 AS named
        FROM payerschedules s
        JOIN payers p ON p.recordid = :p
        WHERE s.accountid = :a AND s.active = 1
          AND (EXISTS (SELECT 1 FROM schedulepayers sp
                        WHERE sp.scheduleid = s.recordid AND sp.payerid = p.recordid)
               OR FIND_IN_SET(p.category, s.payerkinds) > 0)
          AND s.effectivefrom <= :on
          AND (s.effectiveto IS NULL OR s.effectiveto >= :on)
        ORDER BY named DESC, s.effectivefrom DESC
        LIMIT 1
    """, a=accountid, p=payerid, on=on)


FOREVER = "9999-12-31"


def clashes(conn: Connection, accountid: str, *, privatepay: bool, payerkinds: list[str],
            payerids: list[str], effectivefrom, effectiveto,
            scheduleid: str | None = None) -> dict | None:
    """Another live schedule competing with this one at the same level, if there is one.

    Compared level for level, because the levels are a precedence and not a conflict:

      * two cards for the passenger      - a contradiction
      * two cards for brokers            - a contradiction
      * two cards naming ModivCare       - a contradiction
      * a card for brokers AND a card naming ModivCare - the point of the design

    Without that distinction the override would be refused as a clash and the whole scheme
    would collapse back into ticking payers one at a time.
    """
    window = """
        s.accountid = :a AND s.active = 1 AND (:i IS NULL OR s.recordid <> :i)
        AND :from <= COALESCE(s.effectiveto, :forever)
        AND COALESCE(:to, :forever) >= s.effectivefrom
    """
    args = dict(a=accountid, i=scheduleid, forever=FOREVER,
                **{"from": effectivefrom, "to": effectiveto or None})

    if privatepay:
        other = row(conn, f"""
            SELECT s.recordid, s.name, s.effectivefrom, s.effectiveto
            FROM payerschedules s WHERE {window} AND s.privatepay = 1
            ORDER BY s.effectivefrom LIMIT 1
        """, **args)
        if other:
            return {**other, "over": "the passenger"}

    for kind in payerkinds or []:
        other = row(conn, f"""
            SELECT s.recordid, s.name, s.effectivefrom, s.effectiveto
            FROM payerschedules s
            WHERE {window} AND FIND_IN_SET(:k, s.payerkinds) > 0
            ORDER BY s.effectivefrom LIMIT 1
        """, k=kind, **args)
        if other:
            return {**other, "over": CATEGORIES.get(kind, kind).lower()}

    for payerid in payerids or []:
        other = row(conn, f"""
            SELECT s.recordid, s.name, s.effectivefrom, s.effectiveto
            FROM payerschedules s
            WHERE {window}
              AND EXISTS (SELECT 1 FROM schedulepayers sp
                           WHERE sp.scheduleid = s.recordid AND sp.payerid = :p)
            ORDER BY s.effectivefrom LIMIT 1
        """, p=payerid, **args)
        if other:
            name = row(conn, "SELECT name FROM payers WHERE recordid = :i", i=payerid)
            return {**other, "over": name["name"] if name else "that payer"}
    return None


def save_schedule(conn: Connection, accountid: str, userid: str, body: dict,
                  scheduleid: str | None = None) -> str:
    fields = dict(
        name=body["name"].strip()[:120],
        # The passenger, a kind of payer, or named payers. Exactly one of the three is
        # meant, and the screen enforces that; here the others are simply written empty.
        privatepay=1 if body.get("privatepay") else 0,
        payerkinds=",".join(k for k in (body.get("payerkinds") or []) if k in CATEGORIES)
                   or None,
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
            UPDATE payerschedules SET name=:name, privatepay=:privatepay,
                   payerkinds=:payerkinds, contractref=:contractref, effectivefrom=:effectivefrom,
                   effectiveto=:effectiveto, note=:note,
                   active=:active, updated=:now
            WHERE recordid = :i AND accountid = :a
        """, i=scheduleid, a=accountid, now=utcnow(), **fields)
        _set_payers(conn, accountid, scheduleid, body.get("payerids") or [])
        return scheduleid
    scheduleid = newid()
    run(conn, """
        INSERT INTO payerschedules (recordid, accountid, name, privatepay, payerkinds,
                                    contractref, effectivefrom, effectiveto,
                                    note, active, addedby)
        VALUES (:i, :a, :name, :privatepay, :payerkinds, :contractref, :effectivefrom,
                :effectiveto, :note, :active, :by)
    """, i=scheduleid, a=accountid, by=userid, **fields)
    _set_payers(conn, accountid, scheduleid, body.get("payerids") or [])
    return scheduleid


def _set_payers(conn: Connection, accountid: str, scheduleid: str,
                payerids: list[str]) -> None:
    """Replace who this schedule prices.

    Replaced wholesale rather than reconciled: the screen edits a list of ticks and sends the
    list back, and a payer removed from it has to come off. Only payers this company may use
    are accepted - the shared catalogue and its own.
    """
    run(conn, "DELETE FROM schedulepayers WHERE scheduleid = :i", i=scheduleid)
    for payerid in dict.fromkeys(payerids):
        if not row(conn, """
            SELECT 1 AS x FROM payers
            WHERE recordid = :i AND (accountid IS NULL OR accountid = :a)
        """, i=payerid, a=accountid):
            continue
        run(conn, """
            INSERT INTO schedulepayers (scheduleid, payerid, accountid)
            VALUES (:s, :p, :a)
        """, s=scheduleid, p=payerid, a=accountid)


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


def payers(conn: Connection, accountid: str) -> list[dict]:
    """Everyone this company can bill: the shared catalogue, and its own."""
    return rows(conn, f"""
        SELECT p.recordid, p.code, p.name, p.category, p.payerid, p.website, p.notes,
               p.active, p.accountid IS NULL AS shared,
               {", ".join("p." + c for c in ADDRESS)},
               (SELECT COUNT(*) FROM payerdocuments d
                 WHERE d.payerid = p.recordid AND d.accountid = :a) AS documents,
               -- Through the membership list now: a schedule prices several payers, so
               -- the link is a row in schedulepayers rather than a column on the schedule.
               (SELECT COUNT(*) FROM schedulepayers sp
                 WHERE sp.accountid = :a AND sp.payerid = p.recordid) AS schedules
        FROM payers p
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
    """Schedules and trips that would be orphaned by removing this payer."""
    return row(conn, """
        SELECT (SELECT COUNT(*) FROM schedulepayers
                 WHERE accountid = :a AND payerid = :i)
             + (SELECT COUNT(*) FROM trips WHERE accountid = :a AND brokerid = :i) AS n
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
