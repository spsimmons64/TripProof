"""Positions arriving from a tracker in a vehicle - 49 CFR 395 has nothing to say about this,
it is operational.

A device cannot sign in. There is nobody at the wheel of the request, and a login token minted
for a dispatcher has no business in a box that is sold with the van. So this one endpoint takes
a token of its own, held against the account, that can write positions and do nothing else.

Positions are appended, never overwritten. `recordedon` is the moment the fix was TAKEN, which
is not the moment it arrived: a vehicle out of signal reports a backlog when it comes back, and
a trail plotted by arrival time draws a route nobody drove.
"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app.activity import log
from app.db import get_conn, newid, row, run, saved, utcnow
from app.security import account_admin, client_ip

router = APIRouter(prefix="/api", tags=["gps"])

# A fix older than this is history rather than news. Accepted and stored - a backlog is exactly
# what this is for - but it never counts as "reporting now".
STALE = timedelta(hours=24)


class Fix(BaseModel):
    """One position, as a tracker reports it."""
    driver: str                       # recordid, external id or driver number
    vehicle: str | None = None        # the vehicle's external id
    latitude: float
    longitude: float
    recordedon: datetime | None = None
    speed: float | None = None        # mph, as the device reports
    heading: int | None = None        # degrees from north
    accuracy: int | None = None       # metres
    source: str | None = None


class Batch(BaseModel):
    """Several at once, which is how a device that lost signal catches up."""
    fixes: list[Fix]


def _account_for(conn: Connection, token: str | None) -> str:
    if not token:
        raise HTTPException(401, "No GPS token")
    got = row(conn, "SELECT recordid FROM accounts WHERE gpstoken = :t AND gpstoken IS NOT NULL",
              t=token)
    if not got:
        raise HTTPException(401, "That GPS token is not recognised")
    return got["recordid"]


def _driver_in(conn: Connection, acct: str, who: str) -> str | None:
    """The driver a device names, by whichever handle it was configured with."""
    got = row(conn, """
        SELECT recordid FROM drivers
        WHERE accountid = :a AND deleted IS NULL
          AND (recordid = :w OR externalid = :w OR drivernumber = :w)
        LIMIT 1
    """, a=acct, w=who)
    return got["recordid"] if got else None


@router.post("/gps")
def positions_arrived(body: Batch, request: Request,
                      x_gps_token: str | None = Header(default=None),
                      conn: Connection = Depends(get_conn)):
    """Take a position, or a backlog of them, from a vehicle."""
    acct = _account_for(conn, x_gps_token)
    now = utcnow()
    kept, unknown = 0, set()
    for fix in body.fixes:
        if not (-90 <= fix.latitude <= 90 and -180 <= fix.longitude <= 180):
            continue
        driverid = _driver_in(conn, acct, fix.driver)
        if not driverid:
            # Named a driver this account does not have. Said back in the reply rather than
            # failing the batch, because one misconfigured device must not stop a fleet.
            unknown.add(fix.driver)
            continue
        vehicleid = None
        if fix.vehicle:
            got = row(conn, "SELECT recordid FROM vehicles WHERE accountid = :a "
                            "AND externalid = :v AND deleted IS NULL", a=acct, v=fix.vehicle)
            vehicleid = got["recordid"] if got else None
        taken = fix.recordedon or now
        if taken.tzinfo is not None:
            taken = taken.astimezone(timezone.utc).replace(tzinfo=None)
        run(conn, """
            INSERT INTO driverlocations (recordid, accountid, driverid, vehicleid, latitude,
                                         longitude, accuracy, speed, heading, recordedon, source)
            VALUES (:id, :a, :d, :v, :lat, :lng, :acc, :sp, :hd, :on, :src)
        """, id=newid(), a=acct, d=driverid, v=vehicleid, lat=fix.latitude, lng=fix.longitude,
            acc=fix.accuracy, sp=fix.speed, hd=fix.heading, on=taken,
            src=(fix.source or "device")[:32])
        kept += 1
    saved(conn)
    return {"kept": kept, "unknown": sorted(unknown)}


@router.post("/company/gps-token")
def issue_gps_token(request: Request, user: dict = Depends(account_admin),
                    conn: Connection = Depends(get_conn)):
    """Mint this company's GPS token, replacing any it already had.

    Shown once. It is a credential for every tracker in the fleet, so issuing a new one stops
    the old devices until they are reconfigured - which is the point of being able to."""
    token = secrets.token_urlsafe(32)
    run(conn, "UPDATE accounts SET gpstoken = :t, gpstokenon = :now WHERE recordid = :a",
        t=token, now=utcnow(), a=user["accountid"])
    log(conn, user, "gps-token-issued", "company", user["accountid"], {}, ip=client_ip(request))
    saved(conn)
    return {"token": token}
