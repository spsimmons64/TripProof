###################################################################################################
# The facility portal.
#
# A dialysis centre, clinic or hospital on the company's Locations list can be given logins of its
# own. A facility user signs in at /facility and can:
#
#   SEE the day's trips to and from their facility - private pay, and those billed to the facility's
#   contract. Never a broker's trip, and nothing about any other place.
#
#   REQUEST a trip. A request is not a trip: it waits on the office's Dispatch screen until a
#   dispatcher accepts it (booked then, through the same checks as every booking) or declines it with
#   a reason the facility sees. It is tried against those checks the moment it is sent, so a request
#   no driver could take is refused at the facility's desk, not discovered by the office later.
#
#   PRESS READY FOR PICKUP on a will-call return leaving their door: the same thing the office does
#   when the passenger rings, with the word recorded as having come from the facility.
#
#   CANCEL any time. Inside the fee schedule's late-cancel window the facility is told the charge and
#   agrees to it; the cancellation is recorded as the facility's, which is what makes it chargeable.
#
# A facility token carries kind "facility", so it is never taken for an office or driver session.
###################################################################################################
import json
import secrets
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import dispatch, invitations, rates, tripcheck
from app.activity import log
from app.config import settings
from app.db import get_conn, localnow, newid, row, rows, run, saved, utcnow
from app.routers import driverapp
from app.routers import places as placesmod
from app.routers import trips as tripsmod
from app.security import client_ip, current_user, editor, hash_password, verify_password

router = APIRouter(prefix="/api", tags=["facility"])
bearer = HTTPBearer(auto_error=False)
SESSION_HOURS = 12


# -------------------------------------------------------------------------------------------------
# Who is signed in
# -------------------------------------------------------------------------------------------------
def _session(conn: Connection, fu: dict) -> str:
    sid = newid()
    run(conn, "UPDATE facilityusers SET sessionid = :s, lastloginon = :now WHERE recordid = :f",
        s=sid, now=utcnow(), f=fu["recordid"])
    now = utcnow()
    return jwt.encode({"sub": fu["recordid"], "kind": "facility", "sid": sid, "iat": now,
                       "exp": now + timedelta(hours=SESSION_HOURS)}, settings.jwt_secret, algorithm="HS256")


def current_facility(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                     conn: Connection = Depends(get_conn)) -> dict:
    if not creds:
        raise HTTPException(401, "Not signed in")
    try:
        claims = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired. Sign in again.")
    if claims.get("kind") != "facility":
        raise HTTPException(401, "Not a facility session")
    fu = row(conn, """
        SELECT f.recordid, f.accountid, f.placeid, f.name, f.email, f.sessionid, f.closedon,
               p.name AS placename, p.address, p.city, p.state, p.zip, p.critical, p.portal, p.contractpayerid,
               a.name AS accountname, a.phone AS accountphone
        FROM facilityusers f JOIN places p ON p.recordid = f.placeid AND p.deleted IS NULL
        JOIN accounts a ON a.recordid = f.accountid AND a.deleted IS NULL
        WHERE f.recordid = :f
    """, f=claims.get("sub"))
    if not fu or fu["closedon"] or not fu["portal"]:
        raise HTTPException(401, "This login is closed")
    if claims.get("sid") != fu["sessionid"]:
        raise HTTPException(401, "Signed out. Sign in again.")
    fu["full"] = placesmod.full(fu).upper()
    return fu


def _as_user(fu: dict) -> dict:
    """The facility user in the shape the shared trip code writes into its history."""
    return {"accountid": fu["accountid"], "recordid": fu["recordid"], "name": fu["name"]}


class SignIn(BaseModel):
    email: str
    password: str


class SetPassword(BaseModel):
    token: str
    password: str


# One person, one email, possibly several transportation companies. Each company invites and closes
# its own login, and each login sees only that company's trips - nothing is ever combined. The email
# is what ties them together: one password covers them all, sign-in opens the one used last, and the
# portal header switches between the rest.
LIVE_LOGINS = """
    SELECT f.recordid, f.passwordhash, f.lastloginon, a.name AS accountname, p.name AS placename
    FROM facilityusers f
    JOIN places p ON p.recordid = f.placeid AND p.deleted IS NULL AND p.portal = 1
    JOIN accounts a ON a.recordid = f.accountid AND a.deleted IS NULL AND a.status IN ('active', 'setup')
    WHERE LOWER(f.email) = LOWER(:e) AND f.closedon IS NULL AND f.passwordhash IS NOT NULL
"""


@router.post("/facility/signin")
def sign_in(body: SignIn, conn: Connection = Depends(get_conn)):
    """One answer for every failure, so nobody learns which addresses have logins."""
    found = [f for f in rows(conn, LIVE_LOGINS + " ORDER BY f.lastloginon IS NULL, f.lastloginon DESC",
                             e=body.email.strip())
             if verify_password(body.password, f["passwordhash"])]
    if not found:
        raise HTTPException(401, "That email and password do not match.")
    token = _session(conn, found[0])
    saved(conn)
    return {"token": token}


@router.post("/facility/password")
def set_password(body: SetPassword, conn: Connection = Depends(get_conn)):
    """Set a password from an invitation or reset link."""
    if len(body.password) < 10:
        raise HTTPException(400, "Use at least ten characters.")
    t = row(conn, """
        SELECT t.recordid, t.facilityuserid FROM passwordtokens t
        JOIN facilityusers f ON f.recordid = t.facilityuserid AND f.closedon IS NULL
        WHERE t.tokenhash = :h AND t.usedon IS NULL AND t.expires > :now
    """, h=invitations.hash_token(body.token), now=utcnow())
    if not t:
        raise HTTPException(400, "That link has expired. Ask your transportation provider for another.")
    now = utcnow()
    # The link proves the inbox, so the password is the person's: every open login under the same
    # email takes it, whichever company sent this invitation.
    run(conn, """UPDATE facilityusers SET passwordhash = :p, passwordseton = :now
                 WHERE closedon IS NULL AND LOWER(email) = (SELECT e FROM (
                     SELECT LOWER(email) AS e FROM facilityusers WHERE recordid = :f) x)""",
        p=hash_password(body.password), now=now, f=t["facilityuserid"])
    run(conn, "UPDATE passwordtokens SET usedon = :now WHERE recordid = :t", now=now, t=t["recordid"])
    token = _session(conn, {"recordid": t["facilityuserid"]})
    saved(conn)
    return {"token": token}


@router.get("/facility/me")
def who_am_i(fu: dict = Depends(current_facility), conn: Connection = Depends(get_conn)):
    providers = [{"id": f["recordid"], "company": f["accountname"], "place": f["placename"]}
                 for f in rows(conn, LIVE_LOGINS + " ORDER BY a.name", e=fu["email"])]
    return {"name": fu["name"], "place": fu["placename"], "address": fu["full"], "company": fu["accountname"],
            "companyphone": fu["accountphone"], "contract": bool(fu["contractpayerid"]),
            "services": {k: v["label"] for k, v in dispatch.SERVICE.items()},
            "id": fu["recordid"], "providers": providers}


class SwitchIn(BaseModel):
    id: str


@router.post("/facility/switch")
def switch_provider(body: SwitchIn, fu: dict = Depends(current_facility), conn: Connection = Depends(get_conn)):
    """Move to the same person's login at another transportation company - only one under the same
    email, still open, at a company still on TripProof."""
    target = next((f for f in rows(conn, LIVE_LOGINS, e=fu["email"]) if f["recordid"] == body.id), None)
    if not target:
        raise HTTPException(404, "No such provider for this login")
    # The login being left is signed out, so one person holds one session at a time.
    run(conn, "UPDATE facilityusers SET sessionid = :s WHERE recordid = :f", s=newid(), f=fu["recordid"])
    token = _session(conn, target)
    saved(conn)
    return {"token": token}


@router.post("/facility/signout")
def sign_out(fu: dict = Depends(current_facility), conn: Connection = Depends(get_conn)):
    run(conn, "UPDATE facilityusers SET sessionid = :s WHERE recordid = :f", s=newid(), f=fu["recordid"])
    saved(conn)
    return {"ok": True}


# -------------------------------------------------------------------------------------------------
# The facility's schedule
# -------------------------------------------------------------------------------------------------
def _svc(level: str | None) -> str:
    return dispatch.SERVICE.get(level or "", {}).get("label", level or "")


def _clock(v) -> str | None:
    return f"{v:%-I:%M %p}" if v else None


def _trip_is_ours(t: dict, fu: dict) -> bool:
    """Private pay, or billed to this facility's own contract. A broker's trip is the broker's."""
    return t["brokerid"] is None or t["brokerid"] == fu["contractpayerid"]


def _legs_here(conn: Connection, fu: dict, day: date) -> list[dict]:
    return rows(conn, """
        SELECT l.recordid AS legid, l.tripid, l.legnumber, l.pickupat, l.readyabout, l.pickupplace, l.dropoffplace,
               l.driverid, l.executionstate, l.outcomestate, COALESCE(l.brokerstate, t.brokerstate) AS brokerstate,
               t.passenger, t.servicelevel, t.brokerid, t.cancelledon, t.externalid
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        WHERE t.accountid = :a AND t.tripdate = :d
          AND (UPPER(l.pickupplace) = :p OR UPPER(l.dropoffplace) = :p)
          AND (t.brokerid IS NULL OR t.brokerid <=> :c)
        ORDER BY COALESCE(l.pickupat, l.readyabout), l.legnumber
    """, a=fu["accountid"], d=day, p=fu["full"], c=fu["contractpayerid"])


def _status(conn: Connection, fu: dict, l: dict, times: dict) -> tuple[str, str]:
    """What has become of a leg, in two parts: its status, and the latest thing that happened."""
    at = lambda s: _clock(times.get(s))  # noqa: E731
    if l["outcomestate"] == "cancelled" or l["cancelledon"]:
        return "Canceled", ""
    if l["outcomestate"] == "noshow":
        return "No-Show", ""
    if l["outcomestate"]:
        return "Closed", ""
    if l["executionstate"] == "completed":
        return "Completed", f"Dropped off {at('completed')}" if at("completed") else ""
    if l["executionstate"] == "onboard":
        return "Passenger Aboard", f"Picked up {at('onboard')}" if at("onboard") else ""
    if l["executionstate"] == "arrived":
        return "Driver Arrived", f"Arrived {at('arrived')}" if at("arrived") else ""
    if l["executionstate"] == "enroute":
        return "On The Way", f"Set off {at('enroute')}" if at("enroute") else ""
    if l["pickupat"] is None:
        return "Waiting For Call", f"Ready about {_clock(l['readyabout'])}" if l["readyabout"] else ""
    return "Scheduled", "Driver assigned" if l["driverid"] else ""


@router.get("/facility/schedule")
def schedule(day: date | None = None, fu: dict = Depends(current_facility), conn: Connection = Depends(get_conn)):
    zone = dispatch.zone(conn, fu["accountid"])
    day = day or localnow(zone).date()
    legs = _legs_here(conn, fu, day)
    events = {}
    for e in rows(conn, f"""
        SELECT legid, state, MIN(happenedon) AS at FROM tripevents
        WHERE accountid = :a AND legid IN ({",".join(f":l{i}" for i in range(len(legs))) or "''"}) GROUP BY legid, state
    """, a=fu["accountid"], **{f"l{i}": l["legid"] for i, l in enumerate(legs)}):
        events.setdefault(e["legid"], {})[e["state"]] = driverapp._wallclock(conn, fu["accountid"], e["at"])
    items = []
    for l in legs:
        status, progress = _status(conn, fu, l, events.get(l["legid"], {}))
        open_ = status not in ("Canceled", "No-Show", "Closed", "Completed")
        items.append({
            "kind": "trip", "id": l["legid"], "tripid": l["tripid"], "reference": l["externalid"],
            "pickup": _clock(l["pickupat"]) or "Will-Call", "sortat": str(l["pickupat"] or l["readyabout"] or ""),
            "passenger": l["passenger"], "direction": "To Facility" if (l["dropoffplace"] or "").upper() == fu["full"] else "From Facility",
            "service": _svc(l["servicelevel"]),
            "billedto": "Facility Contract" if l["brokerid"] else "Private Pay",
            "status": status, "progress": progress,
            "canready": status == "Waiting For Call" and (l["pickupplace"] or "").upper() == fu["full"]
                        and l["brokerstate"] not in ("returnpending", "returned"),
            "cancancel": open_,
        })
    for r in rows(conn, """
        SELECT recordid, passenger, pickupat, state, declinereason, body FROM triprequests
        WHERE accountid = :a AND placeid = :p AND tripdate = :d AND state IN ('requested', 'declined')
        ORDER BY pickupat
    """, a=fu["accountid"], p=fu["placeid"], d=day):
        b = json.loads(r["body"])
        first = b["legs"][0]
        items.append({
            "kind": "request", "id": r["recordid"], "tripid": None, "reference": None,
            "pickup": _clock(r["pickupat"]), "sortat": str(r["pickupat"]), "passenger": r["passenger"],
            "direction": "To Facility" if (first["dropoffplace"] or "").upper() == fu["full"] else "From Facility",
            "service": _svc(b["servicelevel"]),
            "billedto": "Facility Contract" if b.get("brokerid") else "Private Pay",
            "status": "Requested" if r["state"] == "requested" else "Declined",
            "progress": "Waiting for dispatch" if r["state"] == "requested" else (r["declinereason"] or ""),
            "canready": False, "cancancel": r["state"] == "requested",
        })
    items.sort(key=lambda x: (x["sortat"] == "", x["sortat"]))
    return {"day": str(day), "items": items}


# -------------------------------------------------------------------------------------------------
# Requesting a trip
# -------------------------------------------------------------------------------------------------
class RequestIn(BaseModel):
    passenger: str
    phone: str
    servicelevel: str
    direction: str                 # to | from: to the facility (with an optional return), or from it
    address: str                   # the other end: usually the passenger's home
    tripdate: date
    time: str                      # "15:15": the appointment (to) or the pickup (from)
    returnmode: str = "none"       # to only: time | will | none
    returntime: str | None = None
    billto: str = "private"        # contract | private
    note: str | None = None


def _at(day: date, hhmm: str | None, what: str) -> datetime:
    try:
        h, m = (int(x) for x in (hhmm or "").split(":")[:2])
        return datetime.combine(day, time(h, m))
    except (ValueError, TypeError):
        raise HTTPException(400, f"Give the {what} as hours and minutes") from None


def _booking(conn: Connection, fu: dict, body: RequestIn) -> tripsmod.Booking:
    """The facility's form as the booking it would be."""
    up = lambda v, n: " ".join((v or "").split()).upper()[:n]  # noqa: E731
    who, home = up(body.passenger, 160), up(body.address, 255)
    if not who:
        raise HTTPException(400, "Give the passenger's name.")
    if not home:
        raise HTTPException(400, "Give the passenger's address.")
    if not (body.phone or "").strip():
        raise HTTPException(400, "Give a phone number for the passenger.")
    if body.servicelevel not in dispatch.SERVICE:
        raise HTTPException(400, "Choose the service.")
    if body.billto == "contract" and not fu["contractpayerid"]:
        raise HTTPException(400, "This facility has no contract to bill. Choose private pay.")
    when = _at(body.tripdate, body.time, "appointment" if body.direction == "to" else "pickup time")
    if when < localnow(dispatch.zone(conn, fu["accountid"])):
        raise HTTPException(400, "That time has already passed.")
    legs = []
    if body.direction == "to":
        # Collected early enough to arrive for the appointment, worked out the way the office's
        # booking screen works it out.
        est = placesmod.estimate(home, fu["full"], when, _as_user(fu), conn)
        pickup = datetime.combine(body.tripdate, time(*map(int, est["pickupat"].split(":"))))
        legs.append(tripsmod.Leg(pickupat=pickup, appointmentat=when, pickupplace=home, dropoffplace=fu["full"]))
        if body.returnmode == "time":
            back = _at(body.tripdate, body.returntime, "return pickup time")
            if back <= when:
                raise HTTPException(400, "The return has to be after the appointment.")
            legs.append(tripsmod.Leg(pickupat=back, pickupplace=fu["full"], dropoffplace=home, responsibility="provider"))
        elif body.returnmode == "will":
            legs.append(tripsmod.Leg(pickupat=None, pickupplace=fu["full"], dropoffplace=home, responsibility="provider"))
        elif body.returnmode != "none":
            raise HTTPException(400, "Choose how they come back.")
    elif body.direction == "from":
        legs.append(tripsmod.Leg(pickupat=when, pickupplace=fu["full"], dropoffplace=home))
    else:
        raise HTTPException(400, "Choose to or from the facility.")
    contract = body.billto == "contract"
    return tripsmod.Booking(passenger=who, passengerphone=body.phone.strip()[:32], tripdate=body.tripdate,
                            servicelevel=body.servicelevel, payer="facility" if contract else "private",
                            brokerid=fu["contractpayerid"] if contract else None, critical=bool(fu["critical"]),
                            note=up(body.note, 512) or None, legs=legs)


def try_booking(conn: Connection, user: dict, booking: tripsmod.Booking) -> str | None:
    """Would this book? Every check a booking makes, inside a savepoint that is always rolled back.
    None if it would; otherwise what stops it."""
    sp = conn.begin_nested()
    try:
        tripsmod.book(conn, user, booking)
        return None
    except HTTPException as e:
        return str(e.detail)
    finally:
        sp.rollback()


@router.post("/facility/requests")
def request_a_trip(body: RequestIn, request: Request, fu: dict = Depends(current_facility),
                   conn: Connection = Depends(get_conn)):
    booking = _booking(conn, fu, body)
    stopped = try_booking(conn, _as_user(fu), booking)
    if stopped:
        # The booking check speaks to the office - its hours, its on-call list, its drivers. The
        # facility is told what it can act on: that time cannot be taken, try another or call.
        first = booking.legs[0].pickupat
        call_ = f", or call {fu['accountphone']}" if fu.get("accountphone") else ""
        raise HTTPException(409, f"Not sent. {fu['accountname']} cannot take a trip with a {_clock(first)} pickup on "
                                 f"{first:%m/%d/%Y}. Choose another time{call_}.")
    rid = newid()
    run(conn, """
        INSERT INTO triprequests (recordid, accountid, placeid, facilityuserid, passenger, tripdate, pickupat, body, requestedon)
        VALUES (:id, :a, :p, :f, :who, :d, :at, :b, :now)
    """, id=rid, a=fu["accountid"], p=fu["placeid"], f=fu["recordid"], who=booking.passenger, d=booking.tripdate,
        at=booking.legs[0].pickupat, b=booking.model_dump_json(), now=utcnow())
    log(conn, _as_user(fu), "trip-requested", "triprequest", rid,
        {"place": fu["placename"], "passenger": booking.passenger}, ip=client_ip(request))
    saved(conn)
    return {"recordid": rid, "pickup": _clock(booking.legs[0].pickupat)}


@router.post("/facility/requests/{rid}/withdraw")
def withdraw(rid: str, request: Request, fu: dict = Depends(current_facility), conn: Connection = Depends(get_conn)):
    got = run(conn, """
        UPDATE triprequests SET state = 'withdrawn', decidedon = :now
        WHERE recordid = :r AND accountid = :a AND placeid = :p AND state = 'requested'
    """, now=utcnow(), r=rid, a=fu["accountid"], p=fu["placeid"])
    if not got.rowcount:
        raise HTTPException(409, "That request has already been answered.")
    log(conn, _as_user(fu), "trip-request-withdrawn", "triprequest", rid, {}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


# -------------------------------------------------------------------------------------------------
# Ready for pickup, and cancelling
# -------------------------------------------------------------------------------------------------
def _our_trip(conn: Connection, fu: dict, tripid: str) -> dict:
    t = row(conn, """
        SELECT t.recordid, t.tripdate, t.brokerid, t.servicelevel, t.cancelledon FROM trips t
        WHERE t.recordid = :t AND t.accountid = :a AND t.deleted IS NULL
          AND EXISTS (SELECT 1 FROM triplegs l WHERE l.tripid = t.recordid
                      AND (UPPER(l.pickupplace) = :p OR UPPER(l.dropoffplace) = :p))
    """, t=tripid, a=fu["accountid"], p=fu["full"])
    if not t or not _trip_is_ours(t, fu):
        raise HTTPException(404, "No such trip")
    return t


@router.post("/facility/legs/{legid}/ready")
def ready_for_pickup(legid: str, request: Request, fu: dict = Depends(current_facility),
                     conn: Connection = Depends(get_conn)):
    leg = row(conn, "SELECT tripid, pickupplace FROM triplegs WHERE recordid = :l AND accountid = :a",
              l=legid, a=fu["accountid"])
    if not leg:
        raise HTTPException(404, "No such trip")
    t = _our_trip(conn, fu, leg["tripid"])
    if t["tripdate"] != localnow(dispatch.zone(conn, fu["accountid"])).date():
        raise HTTPException(409, "A ride can only be called on its own day.")
    if (leg["pickupplace"] or "").upper() != fu["full"]:
        raise HTTPException(409, "Only a ride leaving your facility can be called from here.")
    now = localnow(dispatch.zone(conn, fu["accountid"])).replace(second=0, microsecond=0)
    return tripsmod.will_call_answered(legid, tripsmod.CallIn(
        answer="ready", pickupat=now, source="facility", note=f"READY - FROM THE FACILITY PORTAL, {fu['name'].upper()}"),
        request, _as_user(fu), conn)


def late_charge(conn: Connection, acct: str, tripid: str, at: datetime) -> Decimal:
    """What calling this trip off at `at` (UTC) would cost under its fee schedule's late-cancel rate:
    the same rule billing applies afterwards, asked beforehand so the facility is told."""
    t = row(conn, "SELECT tripdate, brokerid, servicelevel FROM trips WHERE recordid = :t", t=tripid)
    legs = rows(conn, """SELECT pickupat, pickupplace FROM triplegs WHERE tripid = :t
                         AND executionstate <> 'completed' AND outcomestate IS NULL""", t=tripid)
    start = next((l["pickupplace"] for l in legs if l["pickupplace"]), None)
    card = rates.in_force(conn, acct, payerid=t["brokerid"], on=t["tripdate"], state=tripcheck.pickup_state(start))
    if not card:
        return Decimal("0")
    late = next((r for r in rows(conn, "SELECT * FROM payerrates WHERE scheduleid = :s AND ratetype = 'latecancel'",
                                 s=card["recordid"]) if (r["servicelevel"] or "") in ("", t["servicelevel"])), None)
    if not late or not late["cancelwithinhours"]:
        return Decimal("0")
    zone = dispatch.zone(conn, acct)
    hit = [l for l in legs if l["pickupat"] and
           (tripsmod._as_instant(l["pickupat"], zone) - at).total_seconds() / 3600 <= float(late["cancelwithinhours"])]
    count = len(hit) if late["unit"] == "leg" else min(1, len(hit))
    return (Decimal(count) * Decimal(str(late["amount"]))).quantize(Decimal("0.01"))


@router.get("/facility/trips/{tripid}/cancel")
def what_cancelling_costs(tripid: str, fu: dict = Depends(current_facility), conn: Connection = Depends(get_conn)):
    _our_trip(conn, fu, tripid)
    return {"charge": float(late_charge(conn, fu["accountid"], tripid, utcnow()))}


class CancelIn(BaseModel):
    charge: float = 0            # the charge the facility was shown and agreed to


@router.post("/facility/trips/{tripid}/cancel")
def cancel(tripid: str, body: CancelIn, request: Request, fu: dict = Depends(current_facility),
           conn: Connection = Depends(get_conn)):
    _our_trip(conn, fu, tripid)
    # Agreed to the charge it carries now, not the one shown a while ago: crossing into the window
    # between looking and pressing Yes is asked again.
    now_charge = late_charge(conn, fu["accountid"], tripid, utcnow())
    if now_charge > Decimal(str(body.charge)):
        raise HTTPException(409, f"Canceling now carries a ${now_charge:.2f} late cancel charge. Ask again.")
    return tripsmod.cancel_trip(tripid, tripsmod.CancelIn(
        reason="facility", note=f"CANCELED FROM THE FACILITY PORTAL BY {fu['name'].upper()}"), request, _as_user(fu), conn)


# -------------------------------------------------------------------------------------------------
# The office: requests on the Dispatch screen
# -------------------------------------------------------------------------------------------------
@router.get("/dispatch/requests")
def open_requests(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Every request waiting for an answer, soonest first, each tried against the booking checks as
    things stand now - a driver free when it was sent may not be free an hour later."""
    acct = user["accountid"]
    out = []
    for r in rows(conn, """
        SELECT r.recordid, r.passenger, r.tripdate, r.pickupat, r.body, r.requestedon,
               p.name AS place, f.name AS requestedby
        FROM triprequests r JOIN places p ON p.recordid = r.placeid JOIN facilityusers f ON f.recordid = r.facilityuserid
        WHERE r.accountid = :a AND r.state = 'requested' ORDER BY r.pickupat
    """, a=acct):
        b = tripsmod.Booking.model_validate_json(r["body"])
        payer = row(conn, "SELECT name FROM payers WHERE recordid = :p", p=b.brokerid) if b.brokerid else None
        back = b.legs[1] if len(b.legs) > 1 else None
        out.append({
            "recordid": r["recordid"], "passenger": r["passenger"], "tripdate": str(r["tripdate"]),
            "pickupat": str(r["pickupat"]), "service": _svc(b.servicelevel),
            "from": b.legs[0].pickupplace, "to": b.legs[0].dropoffplace,
            "returns": None if not back else ("Will-Call" if back.pickupat is None else _clock(back.pickupat)),
            "billedto": payer["name"] if payer else "PRIVATE PAY", "place": r["place"],
            "requestedby": r["requestedby"], "requestedon": str(r["requestedon"]), "note": b.note,
            "check": "The pickup time has passed. Decline it." if _passed(conn, acct, r) else try_booking(conn, user, b),
        })
    return {"items": out}


def _open(conn: Connection, acct: str, rid: str) -> dict:
    r = row(conn, "SELECT * FROM triprequests WHERE recordid = :r AND accountid = :a", r=rid, a=acct)
    if not r:
        raise HTTPException(404, "No such request")
    if r["state"] != "requested":
        raise HTTPException(409, "That request has already been answered.")
    return r


def _passed(conn: Connection, acct: str, r: dict) -> bool:
    """A request whose pickup time has gone by: it can only be declined, never booked into the past."""
    return r["pickupat"] < localnow(dispatch.zone(conn, acct))


@router.post("/dispatch/requests/{rid}/accept")
def accept(rid: str, request: Request, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Booked, through every check a booking makes. Refused the same way a booking is."""
    r = _open(conn, user["accountid"], rid)
    if _passed(conn, user["accountid"], r):
        raise HTTPException(409, "The pickup time has passed. Decline it.")
    got = tripsmod.book(conn, user, tripsmod.Booking.model_validate_json(r["body"]))
    run(conn, "UPDATE triprequests SET state = 'accepted', decidedon = :now, decidedby = :by, tripid = :t WHERE recordid = :r",
        now=utcnow(), by=user["recordid"], t=got["recordid"], r=rid)
    log(conn, user, "trip-request-accepted", "trip", got["recordid"], {"request": rid}, ip=client_ip(request))
    saved(conn)
    return got


class DeclineIn(BaseModel):
    reason: str


@router.post("/dispatch/requests/{rid}/decline")
def decline(rid: str, body: DeclineIn, request: Request, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    why = " ".join((body.reason or "").split()).upper()[:400]
    if not why:
        raise HTTPException(400, "Give the reason the facility will see.")
    _open(conn, user["accountid"], rid)
    run(conn, "UPDATE triprequests SET state = 'declined', decidedon = :now, decidedby = :by, declinereason = :w WHERE recordid = :r",
        now=utcnow(), by=user["recordid"], w=why, r=rid)
    log(conn, user, "trip-request-declined", "triprequest", rid, {"reason": why}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


# -------------------------------------------------------------------------------------------------
# The office: a Location's portal and its logins
# -------------------------------------------------------------------------------------------------
def _place(conn: Connection, acct: str, placeid: str) -> dict:
    p = row(conn, "SELECT * FROM places WHERE recordid = :p AND accountid = :a AND deleted IS NULL", p=placeid, a=acct)
    if not p:
        raise HTTPException(404, "No such location")
    return p


@router.get("/places/{placeid}/portal")
def portal(placeid: str, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    p = _place(conn, acct, placeid)
    logins = rows(conn, """SELECT recordid, name, email, passwordhash IS NOT NULL AS active, closedon, lastloginon
                           FROM facilityusers WHERE accountid = :a AND placeid = :p ORDER BY closedon IS NOT NULL, name""",
                  a=acct, p=placeid)
    for x in logins:
        x["status"] = "Closed" if x.pop("closedon") else ("Active" if x.pop("active") else "Invited")
    payers = rows(conn, "SELECT recordid, name FROM payers WHERE accountid = :a AND active = 1 ORDER BY name", a=acct)
    return {"portal": bool(p["portal"]), "contractpayerid": p["contractpayerid"], "payers": payers, "logins": logins}


class PortalIn(BaseModel):
    portal: bool
    contractpayerid: str | None = None


@router.put("/places/{placeid}/portal")
def set_portal(placeid: str, body: PortalIn, request: Request, user: dict = Depends(editor),
               conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    _place(conn, acct, placeid)
    if body.contractpayerid and not row(conn, "SELECT 1 AS x FROM payers WHERE recordid = :p AND accountid = :a AND active = 1",
                                        p=body.contractpayerid, a=acct):
        raise HTTPException(400, "Choose one of your own payers for the contract.")
    run(conn, "UPDATE places SET portal = :o, contractpayerid = :c WHERE recordid = :p",
        o=int(body.portal), c=body.contractpayerid or None, p=placeid)
    log(conn, user, "place-portal", "place", placeid, body.model_dump(), ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class LoginIn(BaseModel):
    name: str
    email: str


def _invite(conn: Connection, tasks: BackgroundTasks, user: dict, fu: dict, place: dict, purpose: str) -> dict:
    token = secrets.token_urlsafe(32)
    now = utcnow()
    run(conn, "UPDATE passwordtokens SET usedon = :now WHERE facilityuserid = :f AND usedon IS NULL", now=now, f=fu["recordid"])
    run(conn, """INSERT INTO passwordtokens (recordid, facilityuserid, tokenhash, purpose, expires, createdby)
                 VALUES (:id, :f, :h, :p, :exp, :by)""", id=newid(), f=fu["recordid"], h=invitations.hash_token(token),
        p=purpose, exp=invitations.expiry(purpose), by=user["recordid"])
    link = f"{settings.public_url.rstrip('/')}/facility/password?token={token}"
    emailed = invitations.email_configured()
    if emailed:
        tasks.add_task(invitations.deliver, purpose=purpose, name=fu["name"], email=fu["email"], link=link,
                       expires=invitations.expiry(purpose), accountname=f"{user['accountname']} for {place['name']}",
                       staff=False, role="Facility trip requests", invitedby=user["name"], tz=user.get("usertimezone"))
    return {"ok": True, "emailed": emailed, "link": None if emailed else link}


@router.post("/places/{placeid}/logins")
def add_login(placeid: str, body: LoginIn, request: Request, tasks: BackgroundTasks, user: dict = Depends(editor),
              conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    place = _place(conn, acct, placeid)
    name, email = " ".join(body.name.split()).upper()[:120], body.email.strip().lower()[:255]
    if not name:
        raise HTTPException(400, "Give the person's name.")
    if "@" not in email or " " in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(400, "Give their email address.")
    # Once per company. The same person may have a login at another transportation company too -
    # and whether they do is that company's business, so it is neither checked nor said here.
    if row(conn, "SELECT 1 AS x FROM facilityusers WHERE LOWER(email) = :e AND accountid = :a AND closedon IS NULL",
           e=email, a=acct):
        raise HTTPException(409, "That email address already has a facility login with this company.")
    fu = {"recordid": newid(), "name": name, "email": email}
    run(conn, """INSERT INTO facilityusers (recordid, accountid, placeid, name, email, added, addedby)
                 VALUES (:id, :a, :p, :n, :e, :now, :by)""", id=fu["recordid"], a=acct, p=placeid, n=name, e=email,
        now=utcnow(), by=user["recordid"])
    got = _invite(conn, tasks, user, fu, place, "invite")
    log(conn, user, "facility-login-added", "place", placeid, {"name": name, "email": email}, ip=client_ip(request))
    saved(conn)
    return got


def _login(conn: Connection, acct: str, fid: str) -> dict:
    fu = row(conn, "SELECT * FROM facilityusers WHERE recordid = :f AND accountid = :a", f=fid, a=acct)
    if not fu:
        raise HTTPException(404, "No such login")
    return fu


@router.post("/facility-logins/{fid}/invite")
def resend(fid: str, request: Request, tasks: BackgroundTasks, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    fu = _login(conn, acct, fid)
    if fu["closedon"]:
        raise HTTPException(409, "That login is closed.")
    got = _invite(conn, tasks, user, fu, _place(conn, acct, fu["placeid"]), "reset" if fu["passwordhash"] else "invite")
    log(conn, user, "facility-login-invited", "place", fu["placeid"], {"login": fid}, ip=client_ip(request))
    saved(conn)
    return got


@router.post("/facility-logins/{fid}/close")
def close_login(fid: str, request: Request, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    fu = _login(conn, user["accountid"], fid)
    run(conn, "UPDATE facilityusers SET closedon = :now, sessionid = :s WHERE recordid = :f AND closedon IS NULL",
        now=utcnow(), s=newid(), f=fid)
    run(conn, "UPDATE passwordtokens SET usedon = :now WHERE facilityuserid = :f AND usedon IS NULL", now=utcnow(), f=fid)
    log(conn, user, "facility-login-closed", "place", fu["placeid"], {"login": fid}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}
