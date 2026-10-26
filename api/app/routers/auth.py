import time
from collections import defaultdict, deque
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import invitations, signatures
from app.activity import log
from app.db import get_conn, row, run, saved, utcnow
from app.timezones import clean_timezone
import jwt
from fastapi.security import HTTPAuthorizationCredentials

from app.config import settings
from app.security import (SIGNIN_ALLOWED, bearer, client_ip, current_user, hash_password, issue_token,
                          renew_token, verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Login(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: Login, request: Request, conn: Connection = Depends(get_conn)):
    user = row(conn, f"""
        SELECT u.recordid, u.accountid, u.passwordhash FROM users u JOIN accounts a ON a.recordid = u.accountid
        WHERE u.email = :e AND u.deleted IS NULL AND a.deleted IS NULL AND {SIGNIN_ALLOWED}
    """, e=body.email.strip().lower())
    if not user or not verify_password(body.password, user["passwordhash"]):
        log(conn, None, "login-failed", "user", user["recordid"] if user else None,
            {"email": body.email}, ip=client_ip(request), accountid=user["accountid"] if user else None)
        raise HTTPException(401, "Email or password is incorrect")
    run(conn, "UPDATE users SET lastlogin = :now WHERE recordid = :id", now=utcnow(), id=user["recordid"])
    log(conn, user, "login", "user", user["recordid"], ip=client_ip(request))
    return {"token": issue_token(user["recordid"])}


@router.get("/me")
def me(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    # The current subscription's state, for the portal's "payment failed" banner.
    sub = row(conn, """SELECT status, pastduesince, lastpaymenterror FROM subscriptions WHERE accountid = :a
                       ORDER BY status IN ('unpaid', 'canceled', 'incomplete_expired'), startedon DESC, added DESC LIMIT 1""", a=user["accountid"])
    # 49 CFR 382.603. A supervisor who holds the appointment and has not signed their own
    # training record - the banner asks them to, and the question is answered here because
    # this call already runs on every page load. The appointment is the whole trigger: nobody
    # records the training first, so there is nothing else to be waiting for.
    owes = row(conn, """
        SELECT 1 AS x FROM companyroles r
        WHERE r.accountid = :a AND r.userid = :u AND r.role = 'supervisor' AND r.until IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM documentsignatures d
            WHERE d.accountid = r.accountid AND d.ownertype = 'user' AND d.ownerid = r.userid
              AND d.doctype = 'SUPERVISOR_TRAINING_RECORD')
        LIMIT 1
    """, a=user["accountid"], u=user["recordid"])
    return {**user, "subscription": sub, "owessupervisorrecord": bool(owes)}


class MeIn(BaseModel):
    timezone: str | None = None          # "" = the account's time zone


@router.put("/me")
def update_me(body: MeIn, request: Request, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """A user's own settings. Only the time zone for now - it changes how timestamps are shown to them."""
    tz = clean_timezone(body.timezone)
    run(conn, "UPDATE users SET timezone = :tz, updated = :now WHERE recordid = :u", tz=tz, now=utcnow(), u=user["recordid"])
    log(conn, user, "profile-updated", "user", user["recordid"], {"timezone": tz}, ip=client_ip(request))
    acct = row(conn, "SELECT timezone FROM accounts WHERE recordid = (SELECT accountid FROM users WHERE recordid = :u)",
               u=user["recordid"])
    return {"timezone": tz, "usertimezone": tz or acct["timezone"]}


# ------------------------------------------------------------------------------------------------
# The user's own signature
#
# The same model the drivers sign under: one signature per person, created once behind a date of
# birth and a Social Security number, and used for everything they sign afterwards. The first time
# is what fixes the pair; every time after that is checked against it, so a signature on a record
# is a person rather than a session.
# ------------------------------------------------------------------------------------------------

MISS_LIMIT = 6
MISS_WINDOW = 3600
_misses: dict[str, deque] = defaultdict(deque)


def _recent(ip: str | None) -> deque:
    seen = _misses[ip or "-"]
    while seen and time.monotonic() - seen[0] > MISS_WINDOW:
        seen.popleft()
    return seen


class SignatureIn(BaseModel):
    dob: date
    ssn: str
    typedname: str | None = None
    fontkey: str = "modern"


def _prove(conn: Connection, user: dict, ip: str | None, dob: date, ssn: str, *,
           establish: bool) -> dict:
    """Who they say they are.

    The pair guards a signature, so it is checked only where there is a signature to guard, and it
    is fixed only at the moment one is created. A lookup that somebody abandons records nothing -
    otherwise a number mistyped once would lock the right one out for good."""
    if len(_recent(ip)) >= MISS_LIMIT:
        raise HTTPException(429, "Too many tries from here. Wait an hour and try again.")
    if not signatures.valid_ssn(ssn):
        _recent(ip).append(time.monotonic())
        raise HTTPException(400, "That Social Security number doesn't look right")
    if dob >= date.today() or dob.year < 1920:
        raise HTTPException(400, "Check the date of birth")
    sig = signatures.current(conn, user["accountid"], "user", user["recordid"])
    held = row(conn, "SELECT dob, ssnhash FROM users WHERE recordid = :u", u=user["recordid"])
    ssnhash = signatures.ssn_hash(user["accountid"], ssn)
    if sig and held["ssnhash"]:
        if held["ssnhash"] != ssnhash or held["dob"] != dob:
            _recent(ip).append(time.monotonic())
            raise HTTPException(403, "Incorrect Date Of Birth / Social Security Combination")
        try:
            signatures.recognise(conn, user["accountid"], "user", user["recordid"], user["name"], ssn, dob)
        except ValueError as e:
            raise HTTPException(403, str(e))
        return {"signature": sig, "established": False}
    if establish:
        run(conn, "UPDATE users SET dob = :d, ssnhash = :h, updated = :now WHERE recordid = :u",
            d=dob, h=ssnhash, now=utcnow(), u=user["recordid"])
    return {"signature": sig, "established": establish}


def _shown(sig: dict | None, ip: str | None) -> dict | None:
    """A signature as the person signing sees it: the hand, and the stamp that says which signature
    on file it is, when it was adopted and from where - the same things printed under it later."""
    if not sig:
        return None
    return {"recordid": sig["recordid"], "typedname": sig["typedname"], "fontkey": sig["fontkey"],
            "signername": sig["signername"], "verifiedby": sig["verifiedby"],
            "adoptedon": str(sig["createdon"]), "ip": ip}


@router.post("/refresh")
def refresh(user: dict = Depends(current_user),
            creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """The sign-in, extended. Asked for by the office app every few minutes while somebody is using
    it, so a session ends after a stretch with nobody at the keyboard - never part-way through
    somebody's work because a clock set at sign-in ran out. `current_user` has already refused a
    token that is expired, revoked or for an account that may no longer sign in."""
    claims = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
    return {"token": renew_token(claims)}


@router.get("/me/signature")
def my_signature(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Whether this user has a signature yet, and whether they have ever set the pair that unlocks
    it. Nothing of the signature itself is given out until they have proved who they are."""
    held = row(conn, "SELECT ssnhash FROM users WHERE recordid = :u", u=user["recordid"])
    sig = signatures.current(conn, user["accountid"], "user", user["recordid"])
    return {"exists": bool(sig), "identified": held["ssnhash"] is not None, "name": user["name"]}


@router.post("/me/signature/verify")
def verify_me(body: SignatureIn, request: Request, user: dict = Depends(current_user),
              conn: Connection = Depends(get_conn)):
    """Prove it is them, and show them the signature they already have. Nothing is recorded here."""
    sig = _prove(conn, user, client_ip(request), body.dob, body.ssn, establish=False)["signature"]
    return {"ok": True, "signature": _shown(sig, client_ip(request))}


@router.post("/me/signature")
def adopt_my_signature(body: SignatureIn, request: Request, user: dict = Depends(current_user),
                       conn: Connection = Depends(get_conn)):
    """Create the signature, or hand back the one already on file. A person signs with one
    signature - it is not redesigned per document. This is the moment the pair behind it is fixed."""
    sig = _prove(conn, user, client_ip(request), body.dob, body.ssn, establish=True)["signature"]
    if not sig:
        try:
            sig = signatures.adopt(conn, user["accountid"], "user", user["recordid"], user["name"],
                                   body.typedname or user["name"], body.fontkey, "dob_ssn",
                                   client_ip(request), request.headers.get("user-agent"),
                                   email=user.get("email"), role=user.get("role"),
                                   ssn=body.ssn, dob=body.dob)
        except ValueError as e:
            raise HTTPException(400, str(e))
        log(conn, user, "signature-adopted", "user", user["recordid"], ip=client_ip(request))
    saved(conn)
    return _shown(sig, client_ip(request))


# ------------------------------------------------------------------------------------------------
# Password invitations (public - the token is the credential)
# ------------------------------------------------------------------------------------------------

MIN_PASSWORD = 12


@router.get("/reset/{token}")
def check_reset(token: str, conn: Connection = Depends(get_conn)):
    t = invitations.lookup(conn, token)
    if not t:
        raise HTTPException(410, "This link has expired or has already been used. Ask your administrator to send a new one.")
    return {"email": t["email"], "name": t["name"], "accountname": t["accountname"], "purpose": t["purpose"]}


class ResetIn(BaseModel):
    token: str
    password: str


@router.post("/reset")
def do_reset(body: ResetIn, request: Request, conn: Connection = Depends(get_conn)):
    t = invitations.lookup(conn, body.token)
    if not t:
        raise HTTPException(410, "This link has expired or has already been used. Ask your administrator to send a new one.")
    if len(body.password) < MIN_PASSWORD:
        raise HTTPException(400, f"Use at least {MIN_PASSWORD} characters")
    now = utcnow()
    run(conn, "UPDATE users SET passwordhash = :p, updated = :now WHERE recordid = :u",
        p=hash_password(body.password), now=now, u=t["userid"])
    # Spend this link and any other outstanding ones.
    run(conn, "UPDATE passwordtokens SET usedon = :now WHERE userid = :u AND usedon IS NULL", now=now, u=t["userid"])
    user = row(conn, "SELECT recordid, accountid FROM users WHERE recordid = :u", u=t["userid"])
    log(conn, user, "password-set", "user", t["userid"], {"via": t["purpose"]}, ip=client_ip(request))
    run(conn, "UPDATE users SET lastlogin = :now WHERE recordid = :u", now=now, u=t["userid"])
    log(conn, user, "login", "user", t["userid"], ip=client_ip(request))
    # Signed straight in: they just proved control of the address the link went to.
    return {"token": issue_token(t["userid"])}
