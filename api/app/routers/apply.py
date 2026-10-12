###################################################################################################
# The online application - /apply in the web app. Four steps:
#
#   1 start     company details + the admin login. Creates the account in 'setup' (so an unfinished
#               application shows as Setup in the admin portal) and signs the applicant in, so
#               they can leave and come back to finish.
#   2 plan      the fleet size; the subscription tier follows from it (plans are priced by fleet size).
#   3 card      Stripe verifies a card through a SetupIntent confirmed in the browser; the server
#               re-reads the SetupIntent from Stripe and keeps only its ids and brand / last 4 /
#               expiry. The Terms step won't run until this is done.
#   4 complete  acceptance of the current Terms of Service (version + SHA-256 of the exact text,
#               who, when, from where), then the Stripe customer with the card attached, then the
#               subscription on the chosen plan, then the account goes active.
#
# Everything after step 1 needs the applicant's own session, and only while their account is still
# in setup. Without Stripe keys (development) the card step may be skipped; with keys it can't be.
###################################################################################################
import hashlib
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import billing, plans
from app.activity import log
from app.config import settings
from app.db import get_conn, newid, row, run, utcnow
from app.profiles import clean_email, clean_profile
from app.security import client_ip, current_user, hash_password, issue_token

router = APIRouter(prefix="/api/apply", tags=["apply"])

TOS_VERSION = "2026-09-21"
TOS_FILE = Path(__file__).resolve().parents[1] / "legal" / f"terms-{TOS_VERSION}.md"
MIN_PASSWORD = 12
APPLY_FIELDS = ("name", "address1", "address2", "city", "state", "zip", "phone", "fax")

# A small per-IP brake on account creation (applications per hour). In memory, per process - enough
# to blunt a script; put a CAPTCHA in front before a public launch.
START_LIMIT = 10
_starts: dict[str, deque] = defaultdict(deque)


def _rate_limited(ip: str | None) -> bool:
    now, window = time.monotonic(), 3600
    q = _starts[ip or "?"]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= START_LIMIT:
        return True
    q.append(now)
    return False


@lru_cache(maxsize=1)
def terms() -> dict:
    text = TOS_FILE.read_text(encoding="utf-8")
    return {"version": TOS_VERSION, "text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}


def applicant(user: dict = Depends(current_user)) -> dict:
    """The signed-in owner of an account whose application isn't finished yet."""
    if user.get("platformrole") or user.get("launched") or user["role"] != "owner":
        raise HTTPException(403, "Only the applicant can complete an application")
    if user.get("accountstatus") != "setup":
        raise HTTPException(409, "This account's application is already complete")
    return user


def _state(conn: Connection, accountid: str) -> dict:
    a = row(conn, f"""
        SELECT a.recordid, a.accountnumber, {", ".join("a." + f for f in APPLY_FIELDS)}, a.fleetsize, a.planid,
               a.cardbrand, a.cardlast4, a.cardexp, a.cardverifiedon, p.name AS adminname, p.email AS adminemail
        FROM accounts a LEFT JOIN users p ON p.recordid = a.primaryuserid WHERE a.recordid = :id
    """, id=accountid)
    card = {"brand": a["cardbrand"], "last4": a["cardlast4"], "exp": a["cardexp"]} if a["cardverifiedon"] else None
    plan = next((p for p in plans.active_plans(conn) if p["recordid"] == a["planid"]), None)
    # The first step not yet done: plan (2), card (3), terms (4).
    step = 2 if not plan else 3 if not card else 4
    return {"account": {k: a[k] for k in ("accountnumber", *APPLY_FIELDS, "adminname", "adminemail")},
            "fleetsize": a["fleetsize"], "plan": plan, "card": card, "step": step}


# ------------------------------------------------------------------------------------------------
# Public
# ------------------------------------------------------------------------------------------------

@router.get("/config")
def config():
    """What the wizard needs before anyone signs in."""
    return {"stripe": settings.stripe_publishable_key if billing.configured() else None,
            "tosversion": TOS_VERSION}


@router.get("/terms")
def get_terms():
    return terms()


@router.get("/plans")
def get_plans(conn: Connection = Depends(get_conn)):
    """The subscription tiers, by fleet size, for the plan step (and a public pricing page)."""
    return [{k: p[k] for k in ("recordid", "code", "name", "description", "minvehicles", "maxvehicles", "monthlyprice",
                               "trialdays", "features", "contact")} for p in plans.active_plans(conn)]


class StartIn(BaseModel):
    name: str
    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    state: str = "FL"
    zip: str | None = None
    phone: str | None = None
    fax: str | None = None
    adminname: str
    adminemail: str
    password: str
    website: str | None = None      # honeypot: people never see it, form-filling bots do


@router.post("/start")
def start(body: StartIn, request: Request, conn: Connection = Depends(get_conn)):
    ip = client_ip(request)
    if body.website:
        raise HTTPException(400, "Something went wrong. Please try again.")
    if _rate_limited(ip):
        raise HTTPException(429, "Too many applications from this network. Please try again later.")
    profile = clean_profile({k: getattr(body, k) for k in APPLY_FIELDS})
    if not profile.get("address1") or not profile.get("city") or not profile.get("zip") or not profile.get("phone"):
        raise HTTPException(400, "Address, city, ZIP and telephone are required")
    email = clean_email(body.adminemail)
    name = (body.adminname or "").strip()
    if not name:
        raise HTTPException(400, "Your name is required")
    if len(body.password) < MIN_PASSWORD:
        raise HTTPException(400, f"Use a password of at least {MIN_PASSWORD} characters")
    if row(conn, "SELECT 1 AS x FROM users WHERE email = :e", e=email):
        raise HTTPException(409, "That email already has a TripProof login. Sign in to continue your application.")

    acct, uid = newid(), newid()
    number = row(conn, "SELECT NEXT VALUE FOR accountnumbers AS n")["n"]
    cols = ", ".join(profile)
    run(conn, f"""INSERT INTO accounts (recordid, accountnumber, status, signupsource, {cols})
                  VALUES (:id, :num, 'setup', 'online', {", ".join(f":{k}" for k in profile)})""",
        id=acct, num=number, **profile)
    run(conn, """INSERT INTO users (recordid, accountid, email, name, passwordhash, role)
                 VALUES (:id, :a, :e, :n, :p, 'owner')""", id=uid, a=acct, e=email, n=name, p=hash_password(body.password))
    run(conn, "UPDATE accounts SET primaryuserid = :u WHERE recordid = :a", u=uid, a=acct)
    log(conn, {"recordid": uid, "accountid": acct}, "apply-start", "account", acct, {"accountnumber": number}, ip=ip)
    return {"token": issue_token(uid), "accountnumber": number}


# ------------------------------------------------------------------------------------------------
# The applicant's own session, account still in setup
# ------------------------------------------------------------------------------------------------

@router.get("/state")
def state(user: dict = Depends(applicant), conn: Connection = Depends(get_conn)):
    return _state(conn, user["accountid"])


class AccountIn(BaseModel):
    name: str
    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    state: str = "FL"
    zip: str | None = None
    phone: str | None = None
    fax: str | None = None
    adminname: str


@router.put("/account")
def update_account(body: AccountIn, user: dict = Depends(applicant), conn: Connection = Depends(get_conn)):
    """Going back to step 1 after the account exists. The login email is fixed by then."""
    profile = clean_profile({k: getattr(body, k) for k in APPLY_FIELDS})
    if not body.adminname.strip():
        raise HTTPException(400, "Your name is required")
    sets = ", ".join(f"{k} = :{k}" for k in profile)
    run(conn, f"UPDATE accounts SET {sets}, updated = :now WHERE recordid = :a", now=utcnow(), a=user["accountid"], **profile)
    run(conn, "UPDATE users SET name = :n, updated = :now WHERE recordid = :u", n=body.adminname.strip(), now=utcnow(),
        u=user["recordid"])
    return _state(conn, user["accountid"])


class PlanIn(BaseModel):
    fleetsize: int


@router.put("/plan")
def choose_plan(body: PlanIn, user: dict = Depends(applicant), conn: Connection = Depends(get_conn)):
    """Record the fleet size; the plan is the tier that covers it."""
    if body.fleetsize < 1 or body.fleetsize > 100000:
        raise HTTPException(400, "Enter how many vehicles you run")
    plan = plans.plan_for_fleet(conn, body.fleetsize)
    if not plan:
        raise HTTPException(400, "No plan covers that fleet size. Please contact us.")
    if plan["contact"]:
        raise HTTPException(409, f"Fleets of {plan['minvehicles']}+ vehicles are priced individually. Please contact us to set up your account.")
    run(conn, "UPDATE accounts SET fleetsize = :n, planid = :p, updated = :now WHERE recordid = :a",
        n=body.fleetsize, p=plan["recordid"], now=utcnow(), a=user["accountid"])
    return _state(conn, user["accountid"])


@router.post("/card/intent")
def card_intent(user: dict = Depends(applicant), conn: Connection = Depends(get_conn)):
    if not billing.configured():
        raise HTTPException(503, "Card payments aren't set up on this server")
    try:
        si = billing.create_setup_intent(user["accountid"], user["email"])
    except billing.BillingError as e:
        raise HTTPException(402, str(e))
    run(conn, "UPDATE accounts SET stripesetupintentid = :s WHERE recordid = :a", s=si["id"], a=user["accountid"])
    return {"clientsecret": si["client_secret"]}


class VerifyIn(BaseModel):
    skip: bool = False      # development only: allowed just when Stripe isn't configured


@router.post("/card/verify")
def card_verify(body: VerifyIn, request: Request, user: dict = Depends(applicant), conn: Connection = Depends(get_conn)):
    """Ask Stripe whether the card behind this account's SetupIntent was verified. The browser's word
    is never taken for it."""
    if not billing.configured():
        if not body.skip:
            raise HTTPException(400, "Card payments aren't set up on this server")
        card = {"paymentmethod": None, "brand": "none", "last4": None, "exp": None}
    else:
        si = row(conn, "SELECT stripesetupintentid AS s FROM accounts WHERE recordid = :a", a=user["accountid"])["s"]
        if not si:
            raise HTTPException(400, "Start the card check first")
        try:
            card = billing.verified_card(si)
        except billing.BillingError as e:
            raise HTTPException(402, str(e))
    run(conn, """UPDATE accounts SET stripepaymentmethodid = :pm, cardbrand = :b, cardlast4 = :l, cardexp = :x,
                    cardverifiedon = :now WHERE recordid = :a""",
        pm=card["paymentmethod"], b=card["brand"], l=card["last4"], x=card["exp"], now=utcnow(), a=user["accountid"])
    log(conn, user, "apply-card-verified", "account", user["accountid"],
        {"brand": card["brand"], "last4": card["last4"], "skipped": card["paymentmethod"] is None}, ip=client_ip(request))
    return _state(conn, user["accountid"])


class CompleteIn(BaseModel):
    agree: bool
    tosversion: str
    tossha256: str


@router.post("/complete")
def complete(body: CompleteIn, request: Request, user: dict = Depends(applicant), conn: Connection = Depends(get_conn)):
    t = terms()
    if not body.agree:
        raise HTTPException(400, "You need to agree to the Terms of Service")
    if body.tosversion != t["version"] or body.tossha256 != t["sha256"]:
        raise HTTPException(409, "The Terms of Service have changed. Please review the current version.")
    a = row(conn, f"""SELECT recordid, accountnumber, {", ".join(APPLY_FIELDS)}, stripepaymentmethodid, cardverifiedon,
                             fleetsize, planid
                      FROM accounts WHERE recordid = :a FOR UPDATE""", a=user["accountid"])
    plan = row(conn, "SELECT * FROM plans WHERE recordid = :p AND active = 1 AND monthlyprice IS NOT NULL", p=a["planid"])
    if not plan:
        raise HTTPException(400, "Choose a subscription first")
    if not a["cardverifiedon"]:
        raise HTTPException(400, "Verify a payment card first")
    if billing.configured() and not a["stripepaymentmethodid"]:
        raise HTTPException(400, "Verify a payment card first")

    customer, sub = None, None
    if billing.configured():
        try:
            customer = billing.create_customer(a, user["email"], user["name"], a["stripepaymentmethodid"])
            price = billing.ensure_price(plan)
            run(conn, """UPDATE plans SET stripeproductid = :prod, stripepriceid = :price, stripepriceamount = :amt
                         WHERE recordid = :p""", prod=price["stripeproductid"], price=price["stripepriceid"],
                amt=price["stripepriceamount"], p=plan["recordid"])
            sub = billing.create_subscription(customer, price["stripepriceid"], plan["trialdays"], a["recordid"], a["fleetsize"])
        except billing.BillingError as e:
            raise HTTPException(402, str(e))
    ip, now = client_ip(request), utcnow()
    ts = lambda t: datetime.fromtimestamp(t, timezone.utc).replace(tzinfo=None) if t else None
    trialend = ts(sub["trial_end"]) if sub else (now + timedelta(days=plan["trialdays"]) if plan["trialdays"] else None)
    run(conn, """
        INSERT INTO subscriptions (recordid, accountid, planid, status, fleetsize, monthlyprice, stripesubscriptionid,
                                   trialend, currentperiodend, startedon)
        VALUES (:id, :a, :p, :st, :n, :price, :sid, :trial, :pe, :now)
    """, id=newid(), a=a["recordid"], p=plan["recordid"],
        st=sub["status"] if sub else ("trialing" if plan["trialdays"] else "active"), n=a["fleetsize"],
        price=plan["monthlyprice"], sid=sub["id"] if sub else None, trial=trialend,
        pe=ts(sub["current_period_end"]) if sub else None, now=now)
    run(conn, """
        UPDATE accounts SET status = 'active', stripecustomerid = :c, tosversion = :v, tossha256 = :h, tosacceptedon = :now,
               tosacceptedby = :u, tosacceptedip = :ip, applicationcompletedon = :now, updated = :now
        WHERE recordid = :a
    """, c=customer, v=t["version"], h=t["sha256"], now=now, u=user["recordid"], ip=ip, a=user["accountid"])
    log(conn, user, "apply-complete", "account", user["accountid"],
        {"tosversion": t["version"], "tossha256": t["sha256"], "stripecustomer": customer, "plan": plan["code"],
         "fleetsize": a["fleetsize"], "stripesubscription": sub["id"] if sub else None}, ip=ip)
    return {"ok": True, "email": user["email"], "accountnumber": a["accountnumber"]}
