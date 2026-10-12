###################################################################################################
# Trip import - a dispatch CSV export in, trips and legs out.
#
# Same lifecycle as DriverFilesOnline's driverimports:
#   stage   parse + validate once; the parsed rows are sealed into `phi` (they carry member names
#           and addresses); the caller gets a preview. Nothing touches trips yet.
#   commit  write exactly what was previewed, create stub drivers/vehicles for anyone the vault has
#           not seen, evaluate the new trips, and drop the staged PHI.
#   reject  drop the staged PHI and mark the batch rejected.
#
# Ingestion has to be nearly effortless, so headers are matched by synonym (every dispatch system
# names its columns differently) and the caller may override any match with an explicit mapping.
# One file = one batch; the same bytes can be accepted only once (sha256 is unique per account).
###################################################################################################
import csv
import io
import json
import re
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy.engine import Connection

from app import drivers, phi
from app.db import newid, row, rows, run, run_many, utcnow
from app.evaluator import evaluate
from app.storage import sha256

# canonical field -> header synonyms (compared after _norm). Order within a list is priority.
SYNONYMS: dict[str, list[str]] = {
    "tripid":         ["trip id", "tripid", "trip number", "trip no", "trip", "confirmation", "confirmation number",
                       "ride id", "booking id", "invoice number"],
    "leg":            ["leg", "leg number", "leg no", "leg id", "segment"],
    "tripdate":       ["trip date", "date of service", "dos", "service date", "date"],
    "pickupat":       ["actual pickup", "actual pickup time", "pickup time", "pu time", "pickup datetime",
                       "pickup date time", "scheduled pickup", "pickup"],
    "dropoffat":      ["actual dropoff", "actual drop off", "dropoff time", "drop off time", "do time", "dropoff"],
    "driverid":       ["driver id", "driver number", "driver no", "driver code", "employee id"],
    "drivername":     ["driver name", "driver"],
    "vehicleid":      ["vehicle id", "vehicle number", "vehicle no", "unit", "unit number", "unit no", "vehicle"],
    "vin":            ["vin", "vehicle vin"],
    "broker":         ["broker", "payer", "funding source", "funder", "payor"],
    "servicelevel":   ["service level", "level of service", "los", "mode", "space type", "vehicle type"],
    "billedamount":   ["billed amount", "amount billed", "billed", "charge", "charges", "fare", "amount", "total"],
    "billingstatus":  ["billing status", "claim status"],
    "memberid":       ["member id", "medicaid id", "medicaid number", "patient id", "client id", "rider id"],
    "membername":     ["member name", "patient name", "client name", "rider name", "passenger name", "member",
                       "patient", "client", "rider", "passenger"],
    "memberdob":      ["dob", "date of birth", "member dob", "birth date"],
    "pickupaddress":  ["pickup address", "pu address", "from address", "origin", "pickup location"],
    "dropoffaddress": ["dropoff address", "drop off address", "do address", "to address", "destination"],
    "signature":      ["signature", "signed", "member signature", "signature captured"],
    "gps":            ["gps", "gps verified", "gps captured", "gps status"],
}
REQUIRED = ["tripid", "pickupat"]
PHI_FIELDS = ["memberid", "membername", "memberdob", "pickupaddress", "dropoffaddress"]

DATETIME_FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p",
                    "%m/%d/%y %H:%M", "%m/%d/%y %I:%M %p"]
DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"]
TIME_FORMATS = ["%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p", "%I:%M%p"]
SERVICE_LEVELS = {"amb": "ambulatory", "ambulatory": "ambulatory", "wc": "wheelchair", "wheelchair": "wheelchair",
                  "w/c": "wheelchair", "str": "stretcher", "stretcher": "stretcher", "bls": "bls", "als": "als"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (s or "").lower())).strip()


def detect_mapping(headers: list[str]) -> dict[str, str]:
    """canonical field -> header, choosing each header at most once."""
    normed = {_norm(h): h for h in headers}
    used, mapping = set(), {}
    for field, names in SYNONYMS.items():
        for name in names:
            h = normed.get(name)
            if h and h not in used:
                mapping[field] = h
                used.add(h)
                break
    return mapping


def _parse_dt(value: str, fallback_date=None) -> datetime | None:
    v = (value or "").strip()
    if not v:
        return None
    for f in DATETIME_FORMATS:
        try:
            return datetime.strptime(v, f)
        except ValueError:
            pass
    if fallback_date:
        for f in TIME_FORMATS:
            try:
                return datetime.combine(fallback_date, datetime.strptime(v.upper(), f).time())
            except ValueError:
                pass
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(v, f)
        except ValueError:
            pass
    return None


def _parse_date(value: str):
    v = (value or "").strip()
    for f in DATE_FORMATS + DATETIME_FORMATS:
        try:
            return datetime.strptime(v, f).date()
        except ValueError:
            pass
    return None


def _money(value: str) -> Decimal:
    v = re.sub(r"[^0-9.\-]", "", value or "")
    try:
        return Decimal(v).quantize(Decimal("0.01")) if v else Decimal("0.00")
    except InvalidOperation:
        return Decimal("0.00")


def _truthy(value: str) -> bool:
    return _norm(value) in {"y", "yes", "true", "1", "x", "signed", "verified", "captured"}


def _split_name(name: str) -> tuple[str, str]:
    name = (name or "").strip()
    if "," in name:
        last, first = [p.strip() for p in name.split(",", 1)]
        return first, last
    parts = name.split()
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


def parse(data: bytes, mapping: dict[str, str] | None = None) -> dict:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    mapping = {**detect_mapping(headers), **{k: v for k, v in (mapping or {}).items() if v in headers}}
    missing = [f for f in REQUIRED if f not in mapping]
    if missing:
        return {"headers": headers, "mapping": mapping, "rows": [], "errors": [
            {"row": 0, "error": f"No column found for {', '.join(missing)}. Map it and upload again."}]}

    get = lambda r, f: (r.get(mapping[f]) or "").strip() if f in mapping else ""
    parsed, errors = [], []
    for n, r in enumerate(reader, start=2):          # row 1 is the header
        if not any((v or "").strip() for v in r.values()):
            continue
        tripid = get(r, "tripid")
        tripdate = _parse_date(get(r, "tripdate")) if "tripdate" in mapping else None
        pickupat = _parse_dt(get(r, "pickupat"), tripdate)
        if not tripid:
            errors.append({"row": n, "error": "Trip ID is blank"})
            continue
        if not pickupat:
            errors.append({"row": n, "error": f"Pickup time '{get(r, 'pickupat')}' is not a date/time"})
            continue
        leg = get(r, "leg")
        level = _norm(get(r, "servicelevel"))
        parsed.append({
            "row": n,
            "tripid": tripid,
            "leg": int(leg) if leg.isdigit() else None,
            "tripdate": (tripdate or pickupat.date()).isoformat(),
            "pickupat": pickupat.isoformat(sep=" "),
            "dropoffat": (d.isoformat(sep=" ") if (d := _parse_dt(get(r, "dropoffat"), tripdate or pickupat.date())) else None),
            "driverid": get(r, "driverid") or None,
            "drivername": get(r, "drivername") or None,
            "vehicleid": get(r, "vehicleid") or None,
            "vin": get(r, "vin").upper() or None,
            "broker": get(r, "broker") or None,
            "servicelevel": SERVICE_LEVELS.get(level, level or None),
            "billedamount": str(_money(get(r, "billedamount"))),
            "billingstatus": (_norm(get(r, "billingstatus")) or None),
            "signature": _truthy(get(r, "signature")),
            "gps": _truthy(get(r, "gps")),
            "phi": {f: get(r, f) or None for f in PHI_FIELDS},
            "raw": dict(r),
        })
    return {"headers": headers, "mapping": mapping, "rows": parsed, "errors": errors}


# ------------------------------------------------------------------------------------------------
# Matching - against the vault as it is now. Used by both the preview and the commit, so the
# preview's counts are exactly what the commit does.
# ------------------------------------------------------------------------------------------------

def _match_context(conn: Connection, accountid: str) -> dict:
    drivers = rows(conn, "SELECT recordid, externalid, firstname, lastname FROM drivers WHERE accountid = :a AND deleted IS NULL", a=accountid)
    vehicles = rows(conn, "SELECT recordid, externalid, vin FROM vehicles WHERE accountid = :a AND deleted IS NULL", a=accountid)
    brokers = rows(conn, "SELECT recordid, code, name FROM payers "
                         "WHERE category = 'broker'")
    return {
        "driver_ext": {d["externalid"].lower(): d["recordid"] for d in drivers if d["externalid"]},
        "driver_name": {_norm(f"{d['firstname']} {d['lastname']}"): d["recordid"] for d in drivers},
        "vehicle_ext": {v["externalid"].lower(): v["recordid"] for v in vehicles if v["externalid"]},
        "vehicle_vin": {v["vin"].upper(): v["recordid"] for v in vehicles if v["vin"]},
        "brokers": brokers,
    }


def _driver_key(r: dict) -> str | None:
    return (r["driverid"] or r["drivername"] or "").strip().lower() or None


def _vehicle_key(r: dict) -> str | None:
    return (r["vehicleid"] or r["vin"] or "").strip().lower() or None


def _match_driver(ctx: dict, r: dict) -> str | None:
    if r["driverid"] and r["driverid"].lower() in ctx["driver_ext"]:
        return ctx["driver_ext"][r["driverid"].lower()]
    if r["drivername"]:
        first, last = _split_name(r["drivername"])
        return ctx["driver_name"].get(_norm(f"{first} {last}"))
    return None


def _match_vehicle(ctx: dict, r: dict) -> str | None:
    if r["vehicleid"] and r["vehicleid"].lower() in ctx["vehicle_ext"]:
        return ctx["vehicle_ext"][r["vehicleid"].lower()]
    if r["vin"] and r["vin"] in ctx["vehicle_vin"]:
        return ctx["vehicle_vin"][r["vin"]]
    return None


def _match_broker(ctx: dict, value: str | None) -> str | None:
    v = _norm(value or "")
    if not v:
        return None
    for b in ctx["brokers"]:
        if _norm(b["code"]) in v.split() or _norm(b["name"]) in v or v in _norm(b["name"]):
            return b["recordid"]
    return None


def _summarize(conn: Connection, accountid: str, parsed: dict) -> dict:
    ctx = _match_context(conn, accountid)
    rs = parsed["rows"]
    existing = set()
    tripids = sorted({r["tripid"] for r in rs})
    for i in range(0, len(tripids), 500):
        chunk = tripids[i:i + 500]
        p = {f"t{n}": t for n, t in enumerate(chunk)}
        existing |= {x["externalid"] for x in rows(conn, "SELECT externalid FROM trips WHERE accountid = :a AND externalid IN ("
                                                   + ", ".join(f":t{n}" for n in range(len(chunk))) + ")", a=accountid, **p)}
    new_drivers = {_driver_key(r): r["drivername"] or r["driverid"] for r in rs if _driver_key(r) and not _match_driver(ctx, r)}
    new_vehicles = {_vehicle_key(r): r["vehicleid"] or r["vin"] for r in rs if _vehicle_key(r) and not _match_vehicle(ctx, r)}
    brokers_unmatched = sorted({r["broker"] for r in rs if r["broker"] and not _match_broker(ctx, r["broker"])})
    dates = sorted(r["tripdate"] for r in rs)
    return {
        "rowcount": len(rs),
        "tripcount": len(tripids),
        "newtrips": len([t for t in tripids if t not in existing]),
        "duplicatetrips": len(existing),
        "daterange": [dates[0], dates[-1]] if dates else None,
        "totalbilled": str(sum((Decimal(r["billedamount"]) for r in rs), Decimal("0.00"))),
        "newdrivers": sorted(v for v in new_drivers.values() if v),
        "newvehicles": sorted(v for v in new_vehicles.values() if v),
        "legsnodriver": sum(1 for r in rs if not _driver_key(r)),
        "legsnovehicle": sum(1 for r in rs if not _vehicle_key(r)),
        "brokersunmatched": brokers_unmatched,
    }


def _public_batch(b: dict, summary: dict | None, parsed: dict | None) -> dict:
    return {
        "recordid": b["recordid"], "filename": b["filename"], "status": b["status"], "added": b["added"],
        "rowcount": b["rowcount"], "tripcount": b["tripcount"],
        "mapping": json.loads(b["mapping"]) if b.get("mapping") else None,
        "errors": json.loads(b["errors"]) if b.get("errors") else [],
        "headers": parsed["headers"] if parsed else None,
        "fields": list(SYNONYMS.keys()),
        "summary": summary,
    }


def stage(conn: Connection, user: dict, filename: str, data: bytes, mapping: dict | None = None) -> dict:
    acct = user["accountid"]
    digest = sha256(data)
    prior = row(conn, "SELECT recordid, status FROM importbatches WHERE accountid = :a AND sha256 = :h", a=acct, h=digest)
    if prior and prior["status"] == "accepted":
        raise HTTPException(409, "This exact file has already been imported.")
    if prior:
        # A staged or rejected copy of the same file is replaced: re-uploading with a corrected
        # mapping is the normal way to fix a preview.
        phi.delete(conn, acct, "batch", prior["recordid"])
        run(conn, "DELETE FROM importbatches WHERE recordid = :id", id=prior["recordid"])

    parsed = parse(data, mapping)
    batchid = newid()
    run(conn, """
        INSERT INTO importbatches (recordid, accountid, userid, filename, sha256, status, rowcount, tripcount, mapping, errors)
        VALUES (:id, :a, :u, :f, :h, 'staged', :rc, :tc, :m, :e)
    """, id=batchid, a=acct, u=user["recordid"], f=filename[:255], h=digest, rc=len(parsed["rows"]),
        tc=len({r["tripid"] for r in parsed["rows"]}), m=json.dumps(parsed["mapping"]), e=json.dumps(parsed["errors"][:200]))
    phi.put(conn, acct, "batch", batchid, {"rows": parsed["rows"], "headers": parsed["headers"]})
    b = row(conn, "SELECT * FROM importbatches WHERE recordid = :id", id=batchid)
    return _public_batch(b, _summarize(conn, acct, parsed), parsed)


def preview(conn: Connection, user: dict, batchid: str) -> dict:
    b = row(conn, "SELECT * FROM importbatches WHERE recordid = :id AND accountid = :a", id=batchid, a=user["accountid"])
    if not b:
        raise HTTPException(404, "Import not found")
    staged = phi.get(conn, user["accountid"], "batch", batchid) if b["status"] == "staged" else None
    summary = _summarize(conn, user["accountid"], {"rows": staged["rows"]}) if staged else None
    return _public_batch(b, summary, staged)


def reject(conn: Connection, user: dict, batchid: str):
    b = row(conn, "SELECT status FROM importbatches WHERE recordid = :id AND accountid = :a", id=batchid, a=user["accountid"])
    if not b or b["status"] != "staged":
        raise HTTPException(409, "Only a staged import can be rejected")
    phi.delete(conn, user["accountid"], "batch", batchid)
    run(conn, "UPDATE importbatches SET status = 'rejected', decidedon = :now WHERE recordid = :id", now=utcnow(), id=batchid)


def commit(conn: Connection, user: dict, batchid: str) -> dict:
    acct = user["accountid"]
    b = row(conn, "SELECT status FROM importbatches WHERE recordid = :id AND accountid = :a FOR UPDATE", id=batchid, a=acct)
    if not b or b["status"] != "staged":
        raise HTTPException(409, "Only a staged import can be accepted")
    staged = phi.get(conn, acct, "batch", batchid)
    ctx = _match_context(conn, acct)

    # Stub drivers and vehicles for everyone the vault has not seen. They hold no credentials, so
    # their trips surface as exposure until someone completes them.
    created_drivers, created_vehicles = {}, {}
    for r in staged["rows"]:
        dk = _driver_key(r)
        if dk and not _match_driver(ctx, r) and dk not in created_drivers:
            first, last = _split_name(r["drivername"] or r["driverid"])
            did = newid()
            run(conn, """INSERT INTO drivers (recordid, accountid, externalid, drivernumber, firstname, lastname, stub)
                         VALUES (:id, :a, :ext, :num, :f, :l, 1)""", id=did, a=acct, ext=r["driverid"],
                num=drivers.next_number(conn, acct), f=first[:64] or "?", l=last[:64])
            created_drivers[dk] = did
        vk = _vehicle_key(r)
        if vk and not _match_vehicle(ctx, r) and vk not in created_vehicles:
            vid = newid()
            run(conn, """INSERT INTO vehicles (recordid, accountid, externalid, vin, stub)
                         VALUES (:id, :a, :ext, :vin, 1)""", id=vid, a=acct, ext=r["vehicleid"] or r["vin"], vin=r["vin"])
            created_vehicles[vk] = vid

    existing = {t["externalid"] for t in rows(conn, "SELECT externalid FROM trips WHERE accountid = :a", a=acct)}
    trips: "OrderedDict[str, list[dict]]" = OrderedDict()
    for r in staged["rows"]:
        if r["tripid"] not in existing:
            trips.setdefault(r["tripid"], []).append(r)

    trip_rows, leg_rows, newtripids = [], [], []
    for ext, legs in trips.items():
        first = legs[0]
        tid = newid()
        newtripids.append(tid)
        status = first["billingstatus"] if first["billingstatus"] in ("unbilled", "billed", "paid", "held") else "unbilled"
        trip_rows.append({"id": tid, "a": acct, "b": batchid, "ext": ext[:64], "broker": _match_broker(ctx, first["broker"]),
                          "date": first["tripdate"], "level": first["servicelevel"], "status": status,
                          "amt": str(sum((Decimal(l["billedamount"]) for l in legs), Decimal("0.00")))})
        phi.put(conn, acct, "trip", tid, {k: first["phi"].get(k) for k in ("memberid", "membername", "memberdob")})
        legs_sorted = sorted(legs, key=lambda l: (l["leg"] is None, l["leg"] or 0, l["pickupat"]))
        for n, l in enumerate(legs_sorted, start=1):
            lid = newid()
            leg_rows.append({"id": lid, "a": acct, "t": tid, "n": l["leg"] or n,
                             "d": _match_driver(ctx, l) or created_drivers.get(_driver_key(l)),
                             "v": _match_vehicle(ctx, l) or created_vehicles.get(_vehicle_key(l)),
                             "dx": (l["driverid"] or l["drivername"] or None), "vx": (l["vehicleid"] or l["vin"] or None),
                             "p": l["pickupat"], "o": l["dropoffat"], "s": 1 if l["signature"] else 0, "g": 1 if l["gps"] else 0})
            phi.put(conn, acct, "leg", lid, {"pickupaddress": l["phi"].get("pickupaddress"),
                                              "dropoffaddress": l["phi"].get("dropoffaddress"),
                                              "sourcerow": l["row"], "raw": l["raw"]})

    run_many(conn, """
        INSERT INTO trips (recordid, accountid, batchid, externalid, brokerid, tripdate, servicelevel, billingstatus, billedamount)
        VALUES (:id, :a, :b, :ext, :broker, :date, :level, :status, :amt)
    """, trip_rows)
    run_many(conn, """
        INSERT INTO triplegs (recordid, accountid, tripid, legnumber, driverid, vehicleid, driverexternal, vehicleexternal,
                              pickupat, dropoffat, signature, gps)
        VALUES (:id, :a, :t, :n, :d, :v, :dx, :vx, :p, :o, :s, :g)
    """, leg_rows)

    phi.delete(conn, acct, "batch", batchid)
    run(conn, "UPDATE importbatches SET status = 'accepted', decidedon = :now, tripcount = :tc WHERE recordid = :id",
        now=utcnow(), tc=len(newtripids), id=batchid)
    result = evaluate(conn, acct, newtripids, user["recordid"], "import")
    return {"trips": len(newtripids), "legs": len(leg_rows), "skipped": len(staged["rows"]) - len(leg_rows),
            "driverscreated": len(created_drivers), "vehiclescreated": len(created_vehicles), "evaluation": result}
