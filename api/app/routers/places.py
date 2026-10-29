"""The places a company drives to and the passengers it drives - chosen from when a trip is booked,
and added from the same screen when one is not on the list yet."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import routing, wheremap
from app.activity import log
from app.db import get_conn, newid, row, rows, run, saved, utcnow
from app.security import client_ip, current_user, editor

router = APIRouter(prefix="/api", tags=["places"])

# The two lists are the same shape: a name, an address and a telephone number.
KINDS = {"places": "place", "passengers": "passenger"}


class EntryIn(BaseModel):
    name: str
    address: str                     # the street
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    phone: str | None = None
    dob: date | None = None          # passengers only: to be sure who is calling


def full(e: dict) -> str:
    """The whole address on one line, the way a trip carries it: 100 BAY ST, JACKSONVILLE, FL 32202."""
    tail = " ".join(x for x in (e.get("state"), e.get("zip")) if x)
    return ", ".join(x for x in (e.get("address"), e.get("city"), tail) if x)


def _list(conn: Connection, table: str, acct: str) -> list[dict]:
    out = rows(conn, f"""
        SELECT recordid, name, address, city, state, zip, phone{", dob" if table == "passengers" else ""}
        FROM {table} WHERE accountid = :a AND deleted IS NULL ORDER BY name, address
    """, a=acct)
    for e in out:
        e["full"] = full(e)
    return out


def _add(conn: Connection, table: str, body: EntryIn, user: dict, request: Request) -> dict:
    acct = user["accountid"]
    name, address = body.name.strip().upper(), body.address.strip().upper()
    city = (body.city or "").strip().upper()
    state = (body.state or "").strip().upper()
    zipcode = (body.zip or "").strip()
    phone = (body.phone or "").strip() or None
    if not name or not address or not city or not state or not zipcode:
        raise HTTPException(400, "Give the name, the street, the city, the state and the ZIP")
    person = table == "passengers"
    if person:
        if not body.dob:
            raise HTTPException(400, "Give the passenger's date of birth")
        if body.dob >= date.today() or body.dob.year < 1900:
            raise HTTPException(400, "That date of birth cannot be right")
        # A person is the same person by name and date of birth, wherever they live now.
        if row(conn, "SELECT 1 AS x FROM passengers WHERE accountid = :a AND deleted IS NULL "
                     "AND name = :n AND dob = :d", a=acct, n=name, d=body.dob):
            raise HTTPException(409, f"{name}, born {body.dob:%m/%d/%Y}, is already on the list.")
    # The same name at the same address is the one already on the list, not a second of it.
    elif row(conn, "SELECT 1 AS x FROM places WHERE accountid = :a AND deleted IS NULL "
                   "AND name = :n AND address = :ad", a=acct, n=name, ad=address):
        raise HTTPException(409, f"{name} at {address} is already on the list.")
    rid = newid()
    entry = {"address": address, "city": city, "state": state, "zip": zipcode}
    # Where it is, looked up once now: every route to or from it starts here.
    at = wheremap.place(full(entry))
    run(conn, f"""
        INSERT INTO {table} (recordid, accountid, name, address, city, state, zip, lat, lng, phone,
                             added, addedby{", dob" if person else ""})
        VALUES (:id, :a, :n, :ad, :c, :s, :z, :lat, :lng, :p, :now, :by{", :d" if person else ""})
    """, id=rid, a=acct, n=name[:160], ad=address[:255], c=city[:80], s=state[:2], z=zipcode[:10],
        lat=at and at[0], lng=at and at[1], p=phone and phone[:32], now=utcnow(),
        by=user["recordid"], d=body.dob)
    log(conn, user, f"{KINDS[table]}-added", KINDS[table], rid, {"name": name}, ip=client_ip(request))
    saved(conn)
    out = {"recordid": rid, "name": name, **entry, "full": full(entry), "phone": phone}
    return {**out, "dob": body.dob} if person else out


# The list pages: searched, sorted and paged on the server, the way every grid is.
SORTS = {"name": "name", "dob": "dob", "address": "address", "phone": "phone"}


def _page(conn: Connection, table: str, acct: str, q, sort, dir, page, pagesize) -> dict:
    where, params = ["accountid = :a", "deleted IS NULL"], {"a": acct}
    if q and q.strip():
        where.append("(name LIKE :q OR address LIKE :q OR city LIKE :q OR phone LIKE :q)")
        params["q"] = f"%{q.strip()}%"
    clause = " AND ".join(where)
    column = SORTS.get(sort, "name") if sort != "dob" or table == "passengers" else "name"
    direction = "DESC" if str(dir).lower() == "desc" else "ASC"
    pagesize = max(1, min(pagesize, 200))
    total = row(conn, f"SELECT COUNT(*) AS n FROM {table} WHERE {clause}", **params)["n"]
    items = rows(conn, f"""
        SELECT recordid, name, address, city, state, zip, phone{", dob" if table == "passengers" else ""}
        FROM {table} WHERE {clause}
        ORDER BY {column} {direction}, name ASC, recordid ASC LIMIT :lim OFFSET :off
    """, lim=pagesize, off=(max(1, page) - 1) * pagesize, **params)
    for e in items:
        e["full"] = full(e)
    return {"items": items, "total": total, "page": page, "pagesize": pagesize}


def _change(conn: Connection, table: str, rid: str, body: EntryIn, user: dict, request: Request) -> dict:
    """Put an entry right. The address looked up again if it changed; trips already booked keep the
    address they were booked with - this changes the list, not history."""
    acct = user["accountid"]
    held = row(conn, f"SELECT * FROM {table} WHERE recordid = :r AND accountid = :a AND deleted IS NULL",
               r=rid, a=acct)
    if not held:
        raise HTTPException(404, "No such entry")
    name, address = body.name.strip().upper(), body.address.strip().upper()
    city, state = (body.city or "").strip().upper(), (body.state or "").strip().upper()
    zipcode, phone = (body.zip or "").strip(), (body.phone or "").strip() or None
    if not name or not address or not city or not state or not zipcode:
        raise HTTPException(400, "Give the name, the street, the city, the state and the ZIP")
    person = table == "passengers"
    if person:
        if not body.dob:
            raise HTTPException(400, "Give the passenger's date of birth")
        if body.dob >= date.today() or body.dob.year < 1900:
            raise HTTPException(400, "That date of birth cannot be right")
    entry = {"address": address, "city": city, "state": state, "zip": zipcode}
    moved = full(entry) != full(held)
    at = wheremap.place(full(entry)) if moved else None
    run(conn, f"""
        UPDATE {table} SET name = :n, address = :ad, city = :c, state = :s, zip = :z, phone = :p
               {", dob = :d" if person else ""}{", lat = :lat, lng = :lng" if moved else ""}
        WHERE recordid = :r AND accountid = :a
    """, n=name[:160], ad=address[:255], c=city[:80], s=state[:2], z=zipcode[:10], p=phone and phone[:32],
        d=body.dob, lat=at and at[0], lng=at and at[1], r=rid, a=acct)
    log(conn, user, f"{KINDS[table]}-changed", KINDS[table], rid, {"name": name}, ip=client_ip(request))
    saved(conn)
    return {"recordid": rid, "name": name, **entry, "full": full(entry), "phone": phone,
            **({"dob": body.dob} if person else {})}


def _remove(conn: Connection, table: str, rid: str, user: dict, request: Request) -> dict:
    """Off the list. Kept, marked removed: trips booked with it still say where they went."""
    got = run(conn, f"UPDATE {table} SET deleted = :now WHERE recordid = :r AND accountid = :a AND deleted IS NULL",
              now=utcnow(), r=rid, a=user["accountid"])
    if not got.rowcount:
        raise HTTPException(404, "No such entry")
    log(conn, user, f"{KINDS[table]}-removed", KINDS[table], rid, {}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.get("/places")
def list_places(q: str | None = None, sort: str = "name", dir: str = "asc", page: int | None = None,
                pagesize: int = 25, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Every place, for choosing from - or, given a page, one page of them for the list screen."""
    if page:
        return _page(conn, "places", user["accountid"], q, sort, dir, page, pagesize)
    return {"items": _list(conn, "places", user["accountid"])}


@router.put("/places/{rid}")
def change_place(rid: str, body: EntryIn, request: Request, user: dict = Depends(editor),
                 conn: Connection = Depends(get_conn)):
    return _change(conn, "places", rid, body, user, request)


@router.delete("/places/{rid}")
def remove_place(rid: str, request: Request, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    return _remove(conn, "places", rid, user, request)


@router.post("/places")
def add_place(body: EntryIn, request: Request, user: dict = Depends(editor),
              conn: Connection = Depends(get_conn)):
    return _add(conn, "places", body, user, request)


@router.get("/passengers")
def list_passengers(q: str | None = None, sort: str = "name", dir: str = "asc", page: int | None = None,
                    pagesize: int = 25, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    if page:
        return _page(conn, "passengers", user["accountid"], q, sort, dir, page, pagesize)
    return {"items": _list(conn, "passengers", user["accountid"])}


@router.put("/passengers/{rid}")
def change_passenger(rid: str, body: EntryIn, request: Request, user: dict = Depends(editor),
                     conn: Connection = Depends(get_conn)):
    return _change(conn, "passengers", rid, body, user, request)


@router.delete("/passengers/{rid}")
def remove_passenger(rid: str, request: Request, user: dict = Depends(editor),
                     conn: Connection = Depends(get_conn)):
    return _remove(conn, "passengers", rid, user, request)


@router.post("/passengers")
def add_passenger(body: EntryIn, request: Request, user: dict = Depends(editor),
                  conn: Connection = Depends(get_conn)):
    return _add(conn, "passengers", body, user, request)


def _where(conn: Connection, acct: str, address: str) -> tuple[float, float] | None:
    """Where an address is: a passenger's or a place's stored position when it is one of theirs
    (and stored now, if it never was), otherwise looked up."""
    for table in ("passengers", "places"):
        for e in rows(conn, f"SELECT recordid, address, city, state, zip, lat, lng FROM {table} "
                            f"WHERE accountid = :a AND deleted IS NULL", a=acct):
            if full(e) != address:
                continue
            if e["lat"] is not None:
                return float(e["lat"]), float(e["lng"])
            at = wheremap.place(address)
            if at:
                run(conn, f"UPDATE {table} SET lat = :la, lng = :lo WHERE recordid = :r",
                    la=at[0], lo=at[1], r=e["recordid"])
                saved(conn)
            return at
    return wheremap.place(address)


# On top of the drive itself: getting the passenger out and in, and arriving rather than just
# making it.
SPARE = timedelta(minutes=10)


@router.get("/route-estimate")
def estimate(pickup: str, dropoff: str, arrive: datetime, user: dict = Depends(current_user),
             conn: Connection = Depends(get_conn)):
    """The drive from the pickup to the drop-off, and the pickup time that has the passenger there
    by `arrive` (the appointment): the drive and ten minutes before it, to the five minutes below."""
    acct = user["accountid"]
    a, b = _where(conn, acct, pickup.strip().upper()), _where(conn, acct, dropoff.strip().upper())
    if not a or not b:
        raise HTTPException(422, f"{'The pickup' if not a else 'The drop-off'} address could not be found on the map.")
    got = routing.drive(a, b)
    leave = arrive - timedelta(minutes=got["minutes"]) - SPARE
    leave = leave.replace(minute=leave.minute - leave.minute % 5, second=0, microsecond=0)
    return {**got, "pickupat": leave.strftime("%H:%M")}
