###################################################################################################
# The driver's app.
#
# Everything a driver can reach lives behind this prefix and behind `current_driver`, which is a
# different thing from `current_user` and deliberately so. A driver is not a user: they have no
# account-wide permissions, they can see their own assigned work and nothing else, and a token
# minted here carries `kind: "driver"` so that it can never be mistaken for an office session.
# `current_user` looks a subject up in `users`, where a driver's id is not, so the separation
# holds in two ways rather than one.
#
# WHAT THIS MODULE IS CAREFUL ABOUT
#
#   A PHONE IS NOT ON THE NETWORK. A driver drives through dead ground, puts the phone in a
#   pocket, and reports four things at once when the signal comes back. So every event carries the
#   moment it HAPPENED, sent by the device, and the server records both that and its own arrival
#   time. Nothing is rejected for being late.
#
#   THE SAME TAP TWICE IS ONE EVENT. A button pressed again because the first press showed no
#   spinner must not produce two arrivals. State changes are settled by what the leg already says,
#   not by counting presses.
#
#   A DRIVER MAY ONLY TOUCH THEIR OWN WORK. Every query here is filtered by the driver's own id as
#   well as the account's, and the leg is re-read from the database rather than trusted from the
#   request - an app is a thing somebody else can write.
###################################################################################################
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import invitations
from app.config import settings
from app import dispatch
from app.db import get_conn, newid, row, rows, run, saved, utcnow, localnow
from app.security import client_ip, hash_password, verify_password

router = APIRouter(prefix="/api/driver", tags=["driverapp"])
bearer = HTTPBearer(auto_error=False)

# A shift, not a working day: long enough that nobody is signed out mid-trip, short enough that a
# phone left in a vehicle overnight is not an open door.
SHIFT_HOURS = 16

# What a leg can become, and what has to be true before it can. A driver cannot mark a trip
# completed without having collected anybody - the order is the whole point of the record.
NEXT = {
    "scheduled": ("enroute",),
    "enroute": ("arrived",),
    "arrived": ("onboard",),
    "onboard": ("completed",),
    "completed": (),
}
SAID = {"enroute": "On the way", "arrived": "At the pickup", "onboard": "Passenger aboard",
        "completed": "Completed"}

ISSUES = {
    "noshow": "Passenger did not come out",
    "refused": "Passenger refused the ride",
    "address": "Address is wrong or cannot be reached",
    "vehicle": "Something wrong with the vehicle",
    "medical": "Medical problem",
    "traffic": "Held up in traffic",
    "equipment": "Equipment problem",
    "other": "Something else",
}
WAIT_REASONS = {"appointment": "Waiting on the appointment", "passenger": "Waiting on the passenger",
                "facility": "Waiting on the facility", "other": "Something else"}

# Where a driver can legitimately be waiting. Nowhere else, because the word has to mean something
# when it is billed: the fee schedule prices waiting time by the minute, and a clock that can be
# started in the depot before setting off is a clock somebody will eventually have to defend.
#
#   scheduled  has not left yet. Not waiting - not started.
#   enroute    driving. A driver held up on the road has a traffic PROBLEM, not a wait.
#   arrived    at the pickup, passenger not out yet. This is the wait everyone means.
#   onboard    carrying somebody. Driving again.
#   completed  done. Waiting for a return belongs to the RETURN leg, not to the one just driven -
#              a finished trip that can still accrue waiting minutes is a finished trip that can
#              still be added to.
CAN_WAIT = ("arrived",)
WHY_NOT_WAITING = {
    "scheduled": "You have not set off yet, so there is nothing to wait for. Press On The Way "
                 "when you leave.",
    "enroute": "You are on the way. If you are held up, tell the office about it instead.",
    "onboard": "The passenger is with you. If you are held up, tell the office about it instead.",
    "completed": None,          # nothing to say: a finished trip offers nothing at all
}


def start_session(conn: Connection, driverid: str) -> str:
    """Begin a session and end every other one.

    One device at a time. A phone left in a vehicle overnight is a signed-in phone, and whoever
    picks it up next would otherwise be looking at another driver's work and able to complete
    trips in their name. Signing in somewhere new makes every token issued before this moment
    stop working, because they all quote a session id that is no longer the current one."""
    sid = newid()
    run(conn, "UPDATE drivers SET sessionid = :s, lastloginon = :now WHERE recordid = :id",
        s=sid, now=utcnow(), id=driverid)
    now = utcnow()
    return jwt.encode({"sub": driverid, "kind": "driver", "sid": sid, "iat": now,
                       "exp": now + timedelta(hours=SHIFT_HOURS)},
                      settings.jwt_secret, algorithm="HS256")


def current_driver(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                   conn: Connection = Depends(get_conn)) -> dict:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        claims = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    # An office token is not a driver token even though both are signed by us.
    if claims.get("kind") != "driver":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not a driver session")
    held = row(conn, """
        SELECT d.recordid, d.accountid, d.firstname, d.lastname, d.email, d.status, d.appaccess,
               d.sessionid, a.name AS accountname, a.timezone
        FROM drivers d JOIN accounts a ON a.recordid = d.accountid
        WHERE d.recordid = :id AND d.deleted IS NULL
    """, id=claims.get("sub"))
    if not held or not held["appaccess"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This login is closed")
    # Signed in somewhere else since. Said plainly, because the alternative - a session that just
    # stops working - sends a driver to the office believing the app is broken.
    if held["sessionid"] and claims.get("sid") != held["sessionid"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "You signed in on another device, so this one was signed out.")
    return held


# -------------------------------------------------------------------------------------------
# Signing in
# -------------------------------------------------------------------------------------------
class SignIn(BaseModel):
    email: str
    password: str


class SetPassword(BaseModel):
    token: str
    password: str


@router.post("/signin")
def sign_in(body: SignIn, request: Request, conn: Connection = Depends(get_conn)):
    """One answer for every failure.

    Whether the address is unknown, the password wrong, or the login closed, the sentence is the
    same: anything else lets somebody discover who drives for this company by typing addresses in.
    """
    matched = rows(conn, """
        SELECT d.recordid, d.passwordhash, d.appaccess, d.status
        FROM drivers d JOIN accounts a ON a.recordid = d.accountid
        WHERE LOWER(d.email) = LOWER(:e) AND d.deleted IS NULL AND a.status IN ('active', 'setup')
    """, e=body.email.strip())
    # Two driver records can carry the same address - a family sharing one, or a duplicate record
    # nobody has merged. Only those who have actually set a password are candidates, and if that
    # still leaves more than one the login is refused rather than guessed at: signing somebody in
    # as the wrong driver would file their trips against another person's name.
    usable = [d for d in matched if d["passwordhash"] and d["appaccess"]
              and verify_password(body.password, d["passwordhash"])]
    if len(usable) > 1:
        raise HTTPException(409, "That email address is on more than one driver record. "
                                 "The office has to give you one of your own before you can sign in.")
    held = usable[0] if usable else None
    if not held:
        raise HTTPException(401, "That email and password do not match.")
    token = start_session(conn, held["recordid"])
    saved(conn)
    return {"token": token}


@router.post("/password")
def set_password(body: SetPassword, conn: Connection = Depends(get_conn)):
    """Set a password from an invitation or a reset link."""
    if len(body.password) < 10:
        raise HTTPException(400, "Use at least ten characters.")
    found = row(conn, """
        SELECT t.recordid, t.driverid FROM passwordtokens t
        WHERE t.tokenhash = :h AND t.usedon IS NULL AND t.expires > :now
          AND t.driverid IS NOT NULL
    """, h=invitations.hash_token(body.token), now=utcnow())
    if not found:
        raise HTTPException(400, "That link has expired. Ask the office for another.")
    now = utcnow()
    run(conn, "UPDATE drivers SET passwordhash = :p, passwordseton = :now WHERE recordid = :id",
        p=hash_password(body.password), now=now, id=found["driverid"])
    run(conn, "UPDATE passwordtokens SET usedon = :now WHERE recordid = :id",
        now=now, id=found["recordid"])
    token = start_session(conn, found["driverid"])
    saved(conn)
    return {"token": token}


@router.get("/me")
def who_am_i(driver: dict = Depends(current_driver)):
    return {"driverid": driver["recordid"],
            "name": f'{driver["firstname"]} {driver["lastname"]}'.strip(),
            "company": driver["accountname"], "timezone": driver["timezone"],
            "issues": ISSUES, "waitreasons": WAIT_REASONS}


# -------------------------------------------------------------------------------------------
# The work
# -------------------------------------------------------------------------------------------
@router.get("/trips")
def my_work(driver: dict = Depends(current_driver), conn: Connection = Depends(get_conn)):
    """Everything assigned to this driver that is not finished, soonest first, and whatever they
    finished today - so a driver can see what they have already done without ringing in."""
    items = rows(conn, """
        SELECT l.recordid AS legid, l.legnumber, l.pickupat, l.dropoffat, l.executionstate,
               l.outcomestate, l.pickupplace, l.pickuplat, l.pickuplng, l.dropoffplace,
               l.dropofflat, l.dropofflng, l.servicelevel AS legservice,
               t.recordid AS tripid, t.externalid, t.passenger, t.passengerphone, t.servicelevel,
               t.note, l.vehicleid, v.externalid AS vehiclename,
               TRIM(CONCAT(COALESCE(v.modelyear, ''), ' ', COALESCE(v.make, ''), ' ',
                           COALESCE(v.model, ''))) AS vehicledescr,
               (SELECT w.recordid FROM tripwaits w
                 WHERE w.legid = l.recordid AND w.endedon IS NULL LIMIT 1) AS waitingid,
               (SELECT w.startedon FROM tripwaits w
                 WHERE w.legid = l.recordid AND w.endedon IS NULL LIMIT 1) AS waitingsince,
               -- A problem already reported and not yet dealt with. The driver needs to see it
               -- as much as the office does: without it the screen still offers to report a
               -- problem, so the natural thing to do when nothing seems to be happening is to
               -- report it again.
               (SELECT i.recordid FROM tripissues i
                 WHERE i.legid = l.recordid AND i.resolvedon IS NULL
                 ORDER BY i.raisedon DESC LIMIT 1) AS issueid,
               (SELECT i.kind FROM tripissues i
                 WHERE i.legid = l.recordid AND i.resolvedon IS NULL
                 ORDER BY i.raisedon DESC LIMIT 1) AS issuekind,
               (SELECT i.raisedon FROM tripissues i
                 WHERE i.legid = l.recordid AND i.resolvedon IS NULL
                 ORDER BY i.raisedon DESC LIMIT 1) AS issueraisedon,
               (SELECT i.acknowledgedon FROM tripissues i
                 WHERE i.legid = l.recordid AND i.resolvedon IS NULL
                 ORDER BY i.raisedon DESC LIMIT 1) AS issueseen
        FROM triplegs l
        JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        LEFT JOIN vehicles v ON v.recordid = l.vehicleid
        WHERE l.accountid = :a AND l.driverid = :d
          AND (l.executionstate <> 'completed'
               OR DATE(COALESCE(l.dropoffat, l.pickupat)) = :today)
          AND l.outcomestate IS NULL
        ORDER BY l.pickupat IS NULL, l.pickupat, l.legnumber
    """, a=driver["accountid"], d=driver["recordid"], today=_today(conn, driver["accountid"]))
    # A pickup time is already the company's wall clock. The moments the phone reported - when a
    # wait started, when a problem was raised - are UTC instants, and the app shows every time the
    # same way, so they are turned into the same clock here. A driver in Florida told they have
    # been waiting since 5:05 when it is ten past one does not trust the next thing it says.
    here = ZoneInfo(dispatch.zone(conn, driver["accountid"]))
    def local(v):
        return v.replace(tzinfo=timezone.utc).astimezone(here).replace(tzinfo=None) if v else v

    seen = {}
    for i in items:
        for field in ("waitingsince", "issueraisedon", "issueseen"):
            i[field] = local(i[field])
        i["next"] = NEXT.get(i["executionstate"], ())
        i["nextsaid"] = SAID.get(i["next"][0]) if i["next"] else None
        # What this leg will accept, decided here and not in the app. A screen that works out for
        # itself which buttons to show is a second copy of these rules, and the day the two
        # disagree is the day a driver presses something that is refused with no explanation.
        i["canwait"] = i["executionstate"] in CAN_WAIT
        i["whynotwait"] = WHY_NOT_WAITING.get(i["executionstate"])
        # A leg not yet started, in a vehicle that has to be inspected before it goes out today:
        # the check comes first, and where it is enforced the start is not offered at all.
        i["checkfirst"] = (_before_setting_off(conn, driver, i["vehicleid"], seen)
                           if i["executionstate"] == "scheduled" else None)
        if i["checkfirst"] and i["checkfirst"]["enforced"]:
            i["next"] = ()
            i["nextsaid"] = None
        # While the clock runs, ending it is the only thing this leg will accept.
        if i["waitingid"]:
            i["next"] = ()
            i["nextsaid"] = None
        # What the office changed on this trip and this driver has not read. Until they say they
        # have, the leg does not move on: a driver finishing a trip at the old address is the one
        # thing an edit must never cause.
        i["changes"] = _unread(conn, driver, i["legid"], local)
        if i["changes"]:
            i["next"] = ()
            i["nextsaid"] = None
    return {"items": items}


def _unread(conn: Connection, driver: dict, legid: str, local=lambda v: v) -> list[dict]:
    out = []
    for c in rows(conn, """
        SELECT recordid, changedon, changes FROM tripchanges
        WHERE accountid = :a AND legid = :l AND driverid = :d AND seenon IS NULL
        ORDER BY changedon
    """, a=driver["accountid"], l=legid, d=driver["recordid"]):
        out.append({"changeid": c["recordid"], "changedon": local(c["changedon"]),
                    "changes": json.loads(c["changes"] or "[]")})
    return out


@router.post("/legs/{legid}/changes/seen")
def seen_the_change(legid: str, driver: dict = Depends(current_driver),
                    conn: Connection = Depends(get_conn)):
    """The driver has read what the office changed. Recorded with the moment, so the office can see
    that they did and when."""
    _my_leg(conn, driver, legid)
    run(conn, """
        UPDATE tripchanges SET seenon = :now
        WHERE accountid = :a AND legid = :l AND driverid = :d AND seenon IS NULL
    """, now=utcnow(), a=driver["accountid"], l=legid, d=driver["recordid"])
    saved(conn)
    return {"ok": True}


class Moment(BaseModel):
    """When it happened out there, and where. Both optional - a phone with no fix still has a
    driver pressing a button, and losing the event is worse than losing the position."""
    at: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None


class StateIn(Moment):
    state: str
    miles: float | None = None        # how far the leg ran - a distance, never an odometer reading


class WaitIn(Moment):
    reason: str = "appointment"
    note: str | None = None


class IssueIn(Moment):
    kind: str
    note: str | None = None


def _taken(at: datetime | None) -> datetime:
    """When a fix or an event actually happened, as far as we are willing to believe it.

    The device says. That is right for the case this exists for - a phone out of signal reporting
    a backlog - and wrong in one direction: nothing can have happened later than now. A phone with
    a clock a day fast would file positions in the future, where they would sit at the top of
    every "last seen" query for a day, making a vehicle that stopped reporting look like the
    freshest thing on the map. So the past is taken as given and the future is taken as now.
    """
    now = utcnow()
    if at is None:
        return now
    # The device sends naive UTC; anything carrying an offset is reduced to the same.
    said = at.replace(tzinfo=None) if at.tzinfo is None else at.astimezone().replace(tzinfo=None)
    return said if said <= now else now


def _my_leg(conn: Connection, driver: dict, legid: str) -> dict:
    held = row(conn, """
        SELECT l.recordid, l.tripid, l.vehicleid, l.executionstate, l.pickupat, l.dropoffat
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        WHERE l.recordid = :id AND l.accountid = :a AND l.driverid = :d
    """, id=legid, a=driver["accountid"], d=driver["recordid"])
    if not held:
        # Not "forbidden": a driver does not need to learn that a leg exists and is somebody
        # else's. As far as this app is concerned it is not there.
        raise HTTPException(404, "That trip is not on your list")
    return held


def _place(conn: Connection, driver: dict, m: Moment, legid: str | None = None) -> None:
    """A position reported alongside something else is still a position. Filed where every other
    position is filed, so the map and the trail do not have two sources."""
    if m.latitude is None or m.longitude is None:
        return
    run(conn, """
        INSERT INTO driverlocations (recordid, accountid, driverid, vehicleid, latitude, longitude,
                                     accuracy, speed, heading, recordedon, added, source)
        SELECT :id, :a, :d, l.vehicleid, :lat, :lng, NULL, NULL, NULL, :on, :now, 'app'
        FROM triplegs l WHERE l.recordid = :leg
    """, id=newid(), a=driver["accountid"], d=driver["recordid"], lat=m.latitude, lng=m.longitude,
        on=_taken(m.at), now=utcnow(), leg=legid)


def _wallclock(conn: Connection, accountid: str, instant: datetime) -> datetime:
    """A UTC instant as the company's own clock.

    Two kinds of time live in this schema and they are not interchangeable. `tripevents.happenedon`
    is an INSTANT - the moment a phone somewhere pressed a button - and is kept in UTC. But
    `triplegs.pickupat` and `.dropoffat` are BUSINESS times: a 2pm pickup is 2pm in Florida, typed
    that way by the office and shown back exactly as recorded, with nothing converting them.

    Writing the instant straight into those put every drop-off four hours into the future. A leg
    closed at twenty past two read as twenty past six - on the record that is sold as proof of
    when the trip ran, and against which waiting time and trip duration are worked out."""
    return instant.replace(tzinfo=timezone.utc).astimezone(
        ZoneInfo(dispatch.zone(conn, accountid))).replace(tzinfo=None)


@router.post("/legs/{legid}/state")
def move_leg(legid: str, body: StateIn, request: Request,
             driver: dict = Depends(current_driver), conn: Connection = Depends(get_conn)):
    """Move one leg along. The order is enforced: a trip cannot be completed by somebody who never
    said they arrived, because the record of what happened is the thing being sold."""
    leg = _my_leg(conn, driver, legid)
    now = _taken(body.at)
    # Nothing moves while the clock is running. The wait has to be ended deliberately, by the
    # person who started it, standing where it happened - not closed as a side effect of pressing
    # the next thing. A wait that ends because somebody moved on is a wait whose minutes nobody
    # looked at, and those minutes are billed.
    waiting = row(conn, "SELECT startedon FROM tripwaits WHERE legid = :l AND endedon IS NULL "
                        "LIMIT 1", l=legid)
    if waiting and body.state != leg["executionstate"]:
        raise HTTPException(409, "You are still waiting. Press Done Waiting first.")
    if body.state == leg["executionstate"]:
        # The same tap twice. Not an error, not a second event.
        return {"ok": True, "state": leg["executionstate"], "repeat": True}
    if _unread(conn, driver, legid):
        raise HTTPException(409, "The office changed this trip. Read the change and press "
                                 "I Have Seen This first.")
    if body.state not in NEXT.get(leg["executionstate"], ()):
        raise HTTPException(409, f"That trip is already {SAID.get(leg['executionstate'], leg['executionstate']).lower()}.")
    if leg["executionstate"] == "scheduled":
        held = _before_setting_off(conn, driver, leg["vehicleid"], {})
        if held and held["enforced"]:
            raise HTTPException(409, held["why"])
    run(conn, "UPDATE triplegs SET executionstate = :s WHERE recordid = :l", s=body.state, l=legid)
    # The moment itself, kept. `executionstate` says where the leg is; this says when it got there
    # and who was standing where when they said so. Appended, so the sequence survives the next
    # step being taken.
    run(conn, """
        INSERT INTO tripevents (recordid, accountid, legid, state, happenedon, recordedon,
                                driverid, latitude, longitude)
        VALUES (:id, :a, :l, :s, :on, :now, :d, :lat, :lng)
    """, id=newid(), a=driver["accountid"], l=legid, s=body.state, on=now, now=utcnow(),
        d=driver["recordid"], lat=body.latitude, lng=body.longitude)
    # The leg's own pickup and drop-off are business times, not instants - see _wallclock.
    onclock = _wallclock(conn, driver["accountid"], now)
    if body.state == "onboard" and not leg["pickupat"]:
        # A will-call return has no pickup time until somebody collects the passenger.
        run(conn, "UPDATE triplegs SET pickupat = :now WHERE recordid = :l", now=onclock, l=legid)
    if body.state == "completed":
        run(conn, "UPDATE triplegs SET dropoffat = COALESCE(dropoffat, :now) WHERE recordid = :l",
            now=onclock, l=legid)
        if body.miles is not None:
            dispatch.plausible_miles(body.miles)
            run(conn, "UPDATE triplegs SET miles = :m, milessource = 'app' WHERE recordid = :l",
                m=body.miles, l=legid)
        _settle_verify(conn, driver["accountid"], leg["tripid"])

    _place(conn, driver, body, legid)
    saved(conn)
    return {"ok": True, "state": body.state}


@router.post("/legs/{legid}/wait")
def start_waiting(legid: str, body: WaitIn, driver: dict = Depends(current_driver),
                  conn: Connection = Depends(get_conn)):
    """Start the waiting clock. Already running is not an error - it is the same wait."""
    leg = _my_leg(conn, driver, legid)
    if leg["executionstate"] not in CAN_WAIT:
        raise HTTPException(409, WHY_NOT_WAITING.get(
            leg["executionstate"], "You cannot start waiting on this trip yet."))
    open_already = row(conn, "SELECT recordid, startedon FROM tripwaits "
                             "WHERE legid = :l AND endedon IS NULL LIMIT 1", l=legid)
    if open_already:
        return {"ok": True, "waitingid": open_already["recordid"],
                "since": open_already["startedon"], "repeat": True}
    now = _taken(body.at)
    waitid = newid()
    run(conn, """
        INSERT INTO tripwaits (recordid, accountid, legid, driverid, startedon, reason, note,
                               latitude, longitude, added)
        VALUES (:id, :a, :l, :d, :on, :r, :n, :lat, :lng, :now)
    """, id=waitid, a=driver["accountid"], l=legid, d=driver["recordid"], on=now,
        r=body.reason if body.reason in WAIT_REASONS else "other",
        n=(body.note or "").strip()[:300] or None,
        lat=body.latitude, lng=body.longitude, now=utcnow())
    _place(conn, driver, body, legid)
    saved(conn)
    return {"ok": True, "waitingid": waitid, "since": now}


@router.post("/legs/{legid}/wait/end")
def stop_waiting(legid: str, body: Moment, driver: dict = Depends(current_driver),
                 conn: Connection = Depends(get_conn)):
    """Stop the clock and carry on."""
    _my_leg(conn, driver, legid)
    open_already = row(conn, "SELECT recordid, startedon FROM tripwaits "
                             "WHERE legid = :l AND endedon IS NULL LIMIT 1", l=legid)
    if not open_already:
        return {"ok": True, "repeat": True}
    now = _taken(body.at)
    run(conn, "UPDATE tripwaits SET endedon = :now WHERE recordid = :id",
        now=now, id=open_already["recordid"])
    _place(conn, driver, body, legid)
    saved(conn)
    minutes = int(max(0, (now - open_already["startedon"]).total_seconds()) // 60)
    return {"ok": True, "minutes": minutes}


@router.post("/legs/{legid}/issue")
def raise_issue(legid: str, body: IssueIn, driver: dict = Depends(current_driver),
                conn: Connection = Depends(get_conn)):
    """Tell the office something is wrong. It does not end the trip and it does not decide
    anything - a no-show is the broker's procedure to run, not the driver's to declare."""
    leg = _my_leg(conn, driver, legid)
    if body.kind not in ISSUES:
        raise HTTPException(400, "Choose what the problem is")
    # One at a time. A driver who has reported something and seen nothing happen will press the
    # button again - that is the sensible thing to do when a screen gives no sign of having
    # heard you - and the office then gets the same flat tyre twice and has to work out whether
    # it is one problem or two. The screen says what has already been reported; this makes sure
    # of it, because a rule that lives only in a screen is not a rule.
    if row(conn, "SELECT recordid FROM tripissues WHERE legid = :l AND resolvedon IS NULL LIMIT 1",
           l=legid):
        raise HTTPException(409, "You have already told the office. They can see it.")
    run(conn, """
        INSERT INTO tripissues (recordid, accountid, tripid, legid, driverid, kind, note,
                                raisedon, latitude, longitude)
        VALUES (:id, :a, :t, :l, :d, :k, :n, :on, :lat, :lng)
    """, id=newid(), a=driver["accountid"], t=leg["tripid"], l=legid, d=driver["recordid"],
        k=body.kind, n=(body.note or "").strip()[:600] or None, on=_taken(body.at),
        lat=body.latitude, lng=body.longitude)
    _place(conn, driver, body, legid)
    saved(conn)
    return {"ok": True}


class Fixes(BaseModel):
    fixes: list[Moment] = []


@router.post("/positions")
def positions(body: Fixes, driver: dict = Depends(current_driver),
              conn: Connection = Depends(get_conn)):
    """Where this driver has been, in a batch, so a phone that lost signal can catch up.

    Capped per call. A device that has been offline for a day should send its backlog in pieces
    rather than in one request nobody can time out of."""
    kept = 0
    for fix in body.fixes[:200]:
        if fix.latitude is None or fix.longitude is None:
            continue
        run(conn, """
            INSERT INTO driverlocations (recordid, accountid, driverid, latitude, longitude,
                                         recordedon, added, source)
            VALUES (:id, :a, :d, :lat, :lng, :on, :now, 'app')
        """, id=newid(), a=driver["accountid"], d=driver["recordid"], lat=fix.latitude,
            lng=fix.longitude, on=_taken(fix.at), now=utcnow())
        kept += 1
    saved(conn)
    return {"ok": True, "kept": kept}


def _settle_verify(conn: Connection, accountid: str, tripid: str) -> None:
    """A trip whose every leg has been driven is waiting to be read, not ready to be billed."""
    done = row(conn, """
        SELECT COUNT(*) AS legs, SUM(executionstate = 'completed') AS finished
        FROM triplegs WHERE tripid = :t AND accountid = :a
    """, t=tripid, a=accountid) or {}
    if int(done.get("legs") or 0) and int(done.get("finished") or 0) == int(done["legs"]):
        run(conn, "UPDATE trips SET verifystate = 'awaitingreview', updated = :now "
                  "WHERE recordid = :t AND verifystate = 'notready'", now=utcnow(), t=tripid)


# -------------------------------------------------------------------------------------------
# The vehicle check
# -------------------------------------------------------------------------------------------
# 49 CFR 396.11 says the DRIVER prepares the report, at the completion of each day's work on each
# vehicle. Until now one was typed in by whoever was in the office, from whatever the driver said
# on the telephone - which is a record of a conversation, not of an inspection.
#
# 396.13 is the other half and the one people forget: before driving, the driver must review the
# last report and satisfy themselves that anything on it was put right. So the last report is
# shown before a new one is asked for, and an uncorrected defect is said plainly - 396.11(a)(3) does
# not permit the vehicle to be dispatched until the repair is certified.
#
# Nothing here decides anything. A driver reports what they found; whether the van rolls is the
# company's call, recorded by somebody certifying the repair.
DVIR_KINDS = {"pretrip": "Before the shift", "posttrip": "After the shift"}

# The rules that say a vehicle is inspected before it goes out each day, or that a reported defect
# keeps it in until the repair is certified.
DAILY_CHECK = "FL_TRANSIT_DAILY_INSPECTION"
DEFECT_HOLDS = ("FL_TRANSIT_DAILY_INSPECTION", "DVIR")


def _today(conn: Connection, accountid: str):
    """The company's own date. The server's turns over at eight in the evening in Florida."""
    return localnow(dispatch.zone(conn, accountid)).date()


def _before_setting_off(conn: Connection, driver: dict, vehicleid: str | None,
                        seen: dict) -> dict | None:
    """What stands between this driver and setting off in this vehicle today, or None.

    A defect nobody has certified as repaired (49 CFR 396.11(a)(3)), or - where the vehicle runs under
    Florida's bus transit rule - no pre-trip inspection by this driver today. Yesterday's check
    does not cover today's run. Enforced, as the trip check is, only once the rule is approved and
    the company has switched enforcement on; until then the app asks for the check and lets the
    driver go. `seen` keeps the answer per vehicle for one listing."""
    if not vehicleid:
        return None
    if vehicleid in seen:
        return seen[vehicleid]
    from app import facts as factset, rules
    acct = driver["accountid"]
    f = factset.assemble(conn, acct, vehicleid=vehicleid)["facts"]
    reach = {r["code"] for r in rules.for_vehicle(conn, acct, vehicleid, f)
             if r["code"] in DEFECT_HOLDS and r["applies"] is True}
    out = None
    name = (row(conn, "SELECT externalid FROM vehicles WHERE recordid = :v", v=vehicleid)
            or {}).get("externalid") or "this vehicle"
    if reach and row(conn, """
            SELECT 1 AS x FROM vehicledvirs WHERE vehicleid = :v AND accountid = :a
              AND deleted IS NULL AND defects = 1 AND correctedon IS NULL LIMIT 1
            """, v=vehicleid, a=acct):
        out = {"kind": "defect", "rule": next(iter(sorted(reach))),
               "why": f"Vehicle {name} has a reported defect that has not been certified as "
                      f"repaired. It cannot go out until the office certifies the repair."}
    elif DAILY_CHECK in reach and not row(conn, """
            SELECT 1 AS x FROM vehicledvirs WHERE vehicleid = :v AND accountid = :a
              AND driverid = :d AND kind = 'pretrip' AND reportedon = :today AND deleted IS NULL
            LIMIT 1""", v=vehicleid, a=acct, d=driver["recordid"], today=_today(conn, acct)):
        out = {"kind": "pretrip", "rule": DAILY_CHECK,
               "why": f"Do the pre-trip check of vehicle {name} before setting off."}
    if out:
        approved = (row(conn, """SELECT legalreview FROM compliancerules WHERE code = :c
                                 AND accountid IS NULL AND effectiveto IS NULL""", c=out["rule"])
                    or {}).get("legalreview") == "approved"
        switched = bool((row(conn, "SELECT enforcetripcheck FROM companyprofiles WHERE accountid = :a",
                             a=acct) or {}).get("enforcetripcheck"))
        out.update({"vehicleid": vehicleid, "vehiclename": name, "enforced": approved and switched})
    seen[vehicleid] = out
    return out


class CheckIn(BaseModel):
    kind: str
    defects: bool = False
    defectnote: str | None = None
    note: str | None = None
    odometer: int | None = None


@router.get("/vehicles")
def my_vehicles(driver: dict = Depends(current_driver), conn: Connection = Depends(get_conn)):
    """What this driver can report on: whatever they are assigned to today, then the rest of the
    fleet - because a driver sent to collect a different van still has to inspect it."""
    return {"items": rows(conn, """
        SELECT v.recordid, v.externalid, v.make, v.model, v.modelyear,
               EXISTS (SELECT 1 FROM triplegs l
                        WHERE l.vehicleid = v.recordid AND l.driverid = :d
                          AND DATE(COALESCE(l.pickupat, :today)) = :today) AS mine
        FROM vehicles v
        WHERE v.accountid = :a AND v.deleted IS NULL AND v.stub = 0
        ORDER BY mine DESC, v.externalid
    """, a=driver["accountid"], d=driver["recordid"],
         # The driver's today, not the server's. After eight in the evening in Florida the server
         # has already turned over to tomorrow, and the van they are standing next to would drop
         # off the list.
         today=localnow(dispatch.zone(conn, driver["accountid"])).date()), "kinds": DVIR_KINDS}


@router.get("/vehicles/{vehicleid}/lastcheck")
def last_check(vehicleid: str, driver: dict = Depends(current_driver),
               conn: Connection = Depends(get_conn)):
    """The last report on this vehicle, and whether anything on it is still outstanding.

    This is the 396.13 review. A driver about to take a van out is entitled to know what the last
    person to drive it wrote down."""
    acct = driver["accountid"]
    if not row(conn, "SELECT 1 AS x FROM vehicles WHERE recordid = :v AND accountid = :a "
                     "AND deleted IS NULL", v=vehicleid, a=acct):
        raise HTTPException(404, "No such vehicle")
    return {
        "last": row(conn, """
            SELECT r.reportedon, r.kind, r.defects, r.defectnote, r.correctedon, r.correctedby,
                   TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername
            FROM vehicledvirs r LEFT JOIN drivers d ON d.recordid = r.driverid
            WHERE r.vehicleid = :v AND r.accountid = :a AND r.deleted IS NULL
            ORDER BY r.reportedon DESC, r.added DESC LIMIT 1
        """, v=vehicleid, a=acct),
        # The oldest defect nobody has certified. 396.11(a)(3): the vehicle does not go out until it
        # is put right, and a clean report filed afterwards does not lift it.
        "outstanding": row(conn, """
            SELECT r.reportedon, r.defectnote,
                   TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername
            FROM vehicledvirs r LEFT JOIN drivers d ON d.recordid = r.driverid
            WHERE r.vehicleid = :v AND r.accountid = :a AND r.deleted IS NULL
              AND r.defects = 1 AND r.correctedon IS NULL
            ORDER BY r.reportedon ASC, r.added ASC LIMIT 1
        """, v=vehicleid, a=acct),
        "today": rows(conn, """
            SELECT kind, reportedon FROM vehicledvirs
            WHERE vehicleid = :v AND accountid = :a AND driverid = :d AND deleted IS NULL
              AND reportedon = :today
        """, v=vehicleid, a=acct, d=driver["recordid"], today=_today(conn, acct)),
    }


@router.post("/vehicles/{vehicleid}/check")
def file_check(vehicleid: str, body: CheckIn, driver: dict = Depends(current_driver),
               conn: Connection = Depends(get_conn)):
    """File the driver's own inspection report."""
    acct = driver["accountid"]
    if not row(conn, "SELECT 1 AS x FROM vehicles WHERE recordid = :v AND accountid = :a "
                     "AND deleted IS NULL", v=vehicleid, a=acct):
        raise HTTPException(404, "No such vehicle")
    if body.kind not in DVIR_KINDS:
        raise HTTPException(400, "Say whether this is before or after the shift")
    # A defect with nothing said about it is not a report, it is a rumour: the next person has to
    # know what to look at, and the mechanic has to know what to certify.
    if body.defects and not (body.defectnote or "").strip():
        raise HTTPException(400, "Say what is wrong with it.")
    run(conn, """
        INSERT INTO vehicledvirs (recordid, accountid, vehicleid, driverid, reportedon, kind,
                                  defects, defectnote, note, addedby)
        VALUES (:id, :a, :v, :d, :today, :k, :has, :dn, :n, NULL)
    """, id=newid(), a=acct, v=vehicleid, d=driver["recordid"], today=_today(conn, acct), k=body.kind,
        has=1 if body.defects else 0,
        dn=(body.defectnote or "").strip()[:512] or None,
        n=(body.note or "").strip()[:512] or None)
    # The odometer is the vehicle's, not the report's - it is what the mileage rules read, and a
    # driver reading it off the dash once a day is the only reliable source there is.
    if body.odometer is not None and body.odometer > 0:
        run(conn, """
            UPDATE vehicles SET odometer = :o, odometerasof = :today
            WHERE recordid = :v AND accountid = :a
              AND (odometer IS NULL OR odometer <= :o)
        """, o=body.odometer, today=_today(conn, acct), v=vehicleid, a=acct)
    saved(conn)
    return {"ok": True, "defects": bool(body.defects)}
