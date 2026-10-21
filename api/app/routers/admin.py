###################################################################################################
# Admin portal API - TripProof staff only (users.platformrole).
#
#   superadmin   everything below
#   support      read-only: overview, customers, users, credential types, activity
###################################################################################################
import json
import secrets
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import billing, billingsync, emails, gateways, invitations, plans
from app import rates as rateset
from app.profiles import PROFILE_FIELDS, STATUSES, clean_email, clean_profile
from app.timezones import clean_timezone
from app.activity import log
from app.db import get_conn, newid, row, rows, run, utcnow
from app.security import LAUNCH_MINUTES, client_ip, hash_password, issue_launch_token, platform_admin, platform_viewer

router = APIRouter(prefix="/api/admin", tags=["admin"])

def _audit(conn, user, action, entitytype, entityid, detail=None, request: Request | None = None):
    log(conn, user, action, entitytype, entityid, detail, ip=client_ip(request) if request else None)


# ------------------------------------------------------------------------------------------------
# Overview
# ------------------------------------------------------------------------------------------------

@router.get("/overview")
def overview(user: dict = Depends(platform_viewer), conn: Connection = Depends(get_conn)):
    counts = row(conn, """
        SELECT (SELECT COUNT(*) FROM accounts WHERE platform = 0 AND deleted IS NULL) AS customers,
               (SELECT COUNT(*) FROM accounts WHERE platform = 0 AND deleted IS NULL AND status = 'inactive') AS inactive,
               (SELECT COUNT(*) FROM accounts WHERE platform = 0 AND deleted IS NULL AND status = 'setup') AS setup,
               (SELECT COUNT(*) FROM users u JOIN accounts a ON a.recordid = u.accountid
                 WHERE a.platform = 0 AND u.deleted IS NULL) AS users,
               (SELECT COUNT(*) FROM drivers WHERE deleted IS NULL) AS drivers,
               (SELECT COUNT(*) FROM vehicles WHERE deleted IS NULL) AS vehicles,
               (SELECT COUNT(*) FROM trips WHERE deleted IS NULL) AS trips,
               (SELECT COALESCE(SUM(billedamount), 0) FROM trips WHERE deleted IS NULL) AS billed,
               (SELECT COALESCE(SUM(billedamount), 0) FROM tripexposure) AS atrisk,
               (SELECT COUNT(*) FROM credentialtypes WHERE active = 1) AS credentialtypes
    """)
    accounts = rows(conn, """
        SELECT a.recordid, a.name, a.status,
               (SELECT COUNT(*) FROM trips t WHERE t.accountid = a.recordid AND t.deleted IS NULL) AS trips,
               (SELECT COALESCE(SUM(e.billedamount), 0) FROM tripexposure e WHERE e.accountid = a.recordid) AS atrisk
        FROM accounts a WHERE a.platform = 0 AND a.deleted IS NULL
        ORDER BY atrisk DESC LIMIT 8
    """)
    activity = rows(conn, """
        SELECT l.added, l.action, l.entitytype, l.phi, u.name AS username, a.name AS accountname
        FROM activitylog l LEFT JOIN users u ON u.recordid = l.userid LEFT JOIN accounts a ON a.recordid = l.accountid
        ORDER BY l.added DESC LIMIT 12
    """)
    return {"counts": counts, "accounts": accounts, "activity": activity}


# ------------------------------------------------------------------------------------------------
# Customers
# ------------------------------------------------------------------------------------------------

# Setup is assigned by the system to online signups that haven't finished their application; staff
# only ever choose between these two.
STAFF_STATUSES = ("active", "inactive")


class AccountIn(BaseModel):
    name: str
    # Every field in profiles.PROFILE_FIELDS has to be here: create_account reads them all, and one
    # missing (dba, usdot, mcnumber were) crashed every customer created from the admin side.
    dba: str | None = None
    usdot: str | None = None
    mcnumber: str | None = None
    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    county: str | None = None
    state: str = "FL"
    zip: str | None = None
    phone: str | None = None
    fax: str | None = None
    email: str | None = None
    supportemail: str | None = None
    billingemail: str | None = None
    ein: str | None = None
    medicaidid: str | None = None
    npi: str | None = None
    timezone: str = "America/New_York"
    status: str = "active"                  # staff create customers active (or inactive); never setup
    adminname: str
    adminemail: str


class AccountPatch(BaseModel):
    name: str | None = None
    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    county: str | None = None
    state: str | None = None
    zip: str | None = None
    phone: str | None = None
    fax: str | None = None
    email: str | None = None
    supportemail: str | None = None
    billingemail: str | None = None
    ein: str | None = None
    medicaidid: str | None = None
    npi: str | None = None
    timezone: str | None = None
    status: str | None = None
    adminname: str | None = None
    adminemail: str | None = None


# Sortable columns of the customer grid → the SQL they sort by (aliases from the SELECT below).
ACCOUNT_SORTS = {"accountnumber": "a.accountnumber", "name": "a.name", "status": "a.status", "plan": "pl.sortorder",
                 "users": "users", "drivers": "drivers", "vehicles": "vehicles", "trips": "trips", "atrisk": "atrisk"}


@router.get("/accounts")
def list_accounts(q: str | None = None, status: str | None = None, risk: str | None = None,
                  sort: str = "name", dir: str = "asc", page: int = 1, pagesize: int = 25,
                  user: dict = Depends(platform_viewer), conn: Connection = Depends(get_conn)):
    """One page of customers, filtered and sorted. Pickers that need them all ask for a large pagesize.

    Filters: q (name, account #, NPI, city, admin email), status, risk=yes|no (has trips at audit risk).
    Sort: any key of ACCOUNT_SORTS, asc or desc; name breaks ties so paging is stable."""
    pagesize = max(1, min(pagesize, 1000))
    page = max(page, 1)
    direction = "DESC" if dir.lower() == "desc" else "ASC"
    order_by = f"{ACCOUNT_SORTS.get(sort, 'a.name')} {direction}, a.name ASC, a.recordid ASC"
    where = ["a.platform = 0", "a.deleted IS NULL",
             "(:q IS NULL OR CONCAT_WS(' ', a.name, a.npi, a.accountnumber, a.city, p.email) LIKE CONCAT('%', :q, '%'))"]
    params = {"q": q or None}
    if status in STATUSES:
        where.append("a.status = :status"); params["status"] = status
    if risk in ("yes", "no"):
        where.append(("" if risk == "yes" else "NOT ") + "EXISTS (SELECT 1 FROM tripexposure e WHERE e.accountid = a.recordid)")
    clause = " AND ".join(where)
    total = row(conn, f"SELECT COUNT(*) AS n FROM accounts a LEFT JOIN users p ON p.recordid = a.primaryuserid WHERE {clause}",
                **params)["n"]
    items = rows(conn, f"""
        SELECT a.recordid, a.accountnumber, a.name, a.city, a.state, a.status, a.npi, a.added, p.email AS adminemail,
               pl.name AS planname, a.fleetsize, a.holdreason,
               (SELECT s.status FROM subscriptions s WHERE s.accountid = a.recordid
                ORDER BY s.status IN ('unpaid', 'canceled', 'incomplete_expired'), s.startedon DESC, s.added DESC LIMIT 1) AS substatus,
               (SELECT COUNT(*) FROM users u WHERE u.accountid = a.recordid AND u.deleted IS NULL) AS users,
               (SELECT COUNT(*) FROM drivers d WHERE d.accountid = a.recordid AND d.deleted IS NULL) AS drivers,
               (SELECT COUNT(*) FROM vehicles v WHERE v.accountid = a.recordid AND v.deleted IS NULL) AS vehicles,
               (SELECT COUNT(*) FROM trips t WHERE t.accountid = a.recordid AND t.deleted IS NULL) AS trips,
               (SELECT COALESCE(SUM(e.billedamount), 0) FROM tripexposure e WHERE e.accountid = a.recordid) AS atrisk
        FROM accounts a LEFT JOIN users p ON p.recordid = a.primaryuserid LEFT JOIN plans pl ON pl.recordid = a.planid
        WHERE {clause}
        ORDER BY {order_by}
        LIMIT :lim OFFSET :off
    """, lim=pagesize, off=(page - 1) * pagesize, **params)
    return {"total": total, "page": page, "pagesize": pagesize, "items": items}


@router.post("/accounts")
def create_account(body: AccountIn, request: Request, background: BackgroundTasks, user: dict = Depends(platform_admin),
                   conn: Connection = Depends(get_conn)):
    """A new customer: the account (numbered from the sequence) and its admin login, who is emailed
    an invitation to set a password."""
    profile = clean_profile({k: getattr(body, k) for k in PROFILE_FIELDS})
    if body.status not in STAFF_STATUSES:
        raise HTTPException(400, "Status must be active or inactive")
    profile["status"] = body.status
    email = clean_email(body.adminemail)
    if not (body.adminname or "").strip():
        raise HTTPException(400, "Admin name is required")
    acct = newid()
    number = row(conn, "SELECT NEXT VALUE FOR accountnumbers AS n")["n"]
    cols = ", ".join(profile)
    run(conn, f"""INSERT INTO accounts (recordid, accountnumber, timezone, {cols})
                  VALUES (:id, :num, :tz, {", ".join(f":{k}" for k in profile)})""",
        id=acct, num=number, tz=body.timezone, **profile)
    admin = _create_user(conn, acct, email, body.adminname.strip(), "owner", None)
    run(conn, "UPDATE accounts SET primaryuserid = :u WHERE recordid = :id", u=admin["recordid"], id=acct)
    invite = _invite(conn, background, admin["recordid"], "invite", user)
    _audit(conn, user, "admin-create-account", "account", acct, {"name": profile["name"], "accountnumber": number}, request)
    return {"recordid": acct, "accountnumber": number, "invitation": invite}


@router.get("/accounts/{accountid}")
def get_account(accountid: str, user: dict = Depends(platform_viewer), conn: Connection = Depends(get_conn)):
    a = row(conn, """
        SELECT a.*, p.name AS adminname, p.email AS adminemail, p.lastlogin AS adminlastlogin
        FROM accounts a LEFT JOIN users p ON p.recordid = a.primaryuserid
        WHERE a.recordid = :id AND a.deleted IS NULL
    """, id=accountid)
    if not a:
        raise HTTPException(404, "Account not found")
    a["users"] = rows(conn, """
        SELECT u.recordid, u.email, u.name, u.role, u.platformrole, u.timezone, u.lastlogin, u.added, u.deleted,
               (SELECT MAX(t.added) FROM passwordtokens t WHERE t.userid = u.recordid) AS lastinvited,
               EXISTS (SELECT 1 FROM activitylog l WHERE l.userid = u.recordid AND l.action = 'password-set') AS passwordset
        FROM users u WHERE u.accountid = :id ORDER BY u.deleted IS NOT NULL, u.name
    """, id=accountid)
    a["stats"] = row(conn, """
        SELECT (SELECT COUNT(*) FROM drivers WHERE accountid = :id AND deleted IS NULL) AS drivers,
               (SELECT COUNT(*) FROM drivers WHERE accountid = :id AND deleted IS NULL AND stub = 1) AS stubdrivers,
               (SELECT COUNT(*) FROM vehicles WHERE accountid = :id AND deleted IS NULL) AS vehicles,
               (SELECT COUNT(*) FROM trips WHERE accountid = :id AND deleted IS NULL) AS trips,
               (SELECT COALESCE(SUM(billedamount), 0) FROM trips WHERE accountid = :id AND deleted IS NULL) AS billed,
               (SELECT COUNT(*) FROM tripexposure WHERE accountid = :id) AS risktrips,
               (SELECT COALESCE(SUM(billedamount), 0) FROM tripexposure WHERE accountid = :id) AS atrisk,
               (SELECT COUNT(*) FROM credentials WHERE accountid = :id AND deleted IS NULL) AS credentials,
               (SELECT COUNT(*) FROM auditpackets WHERE accountid = :id) AS packets,
               (SELECT MAX(added) FROM importbatches WHERE accountid = :id AND status = 'accepted') AS lastimport
    """, id=accountid)
    a["activity"] = rows(conn, """
        SELECT l.added, l.action, l.entitytype, l.phi, u.name AS username
        FROM activitylog l LEFT JOIN users u ON u.recordid = l.userid
        WHERE l.accountid = :id ORDER BY l.added DESC LIMIT 25
    """, id=accountid)
    a["emailconfigured"] = invitations.email_configured()
    a["subscription"] = billingsync.current_subscription(conn, accountid)
    a["invoices"] = rows(conn, """
        SELECT stripeinvoiceid, number, status, amountdue, amountpaid, periodstart, periodend, paidon, invoicedon,
               attemptcount, nextattempt, failuremessage, hostedurl, pdfurl
        FROM invoices WHERE accountid = :id AND status <> 'draft' ORDER BY invoicedon DESC, added DESC LIMIT 200
    """, id=accountid)
    a["stripedashboard"] = billing.dashboard_url(a["stripecustomerid"]) if a.get("stripecustomerid") else None
    return a


@router.patch("/accounts/{accountid}")
def patch_account(accountid: str, body: AccountPatch, request: Request, user: dict = Depends(platform_admin),
                  conn: Connection = Depends(get_conn)):
    """Profile edits. The account number never changes. Admin name/email edit the primary login
    itself - changing the email changes the address that user signs in with."""
    a = row(conn, "SELECT platform, primaryuserid FROM accounts WHERE recordid = :id AND deleted IS NULL", id=accountid)
    if not a:
        raise HTTPException(404, "Account not found")
    sent = body.model_dump(exclude_unset=True)
    fields = clean_profile({k: v for k, v in sent.items() if k in PROFILE_FIELDS})
    if "timezone" in sent and sent["timezone"]:
        fields["timezone"] = sent["timezone"]
    if "status" in sent:
        current = row(conn, "SELECT status FROM accounts WHERE recordid = :id", id=accountid)["status"]
        # Staff can move an account to active or inactive; "setup" can only be kept, never chosen.
        if sent["status"] not in STAFF_STATUSES and sent["status"] != current:
            raise HTTPException(400, "Status must be active or inactive")
        if a["platform"]:
            raise HTTPException(400, "The platform account cannot be made inactive")
        fields["status"] = sent["status"]
        if sent["status"] != current:
            fields["holdreason"] = None     # staff's call replaces any billing hold
    if fields:
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        run(conn, f"UPDATE accounts SET {sets}, updated = :now WHERE recordid = :id", now=utcnow(), id=accountid, **fields)
    admin = {}
    if a["primaryuserid"] and ("adminname" in sent or "adminemail" in sent):
        if sent.get("adminname") is not None:
            if not sent["adminname"].strip():
                raise HTTPException(400, "Admin name is required")
            admin["name"] = sent["adminname"].strip()
        if sent.get("adminemail") is not None:
            admin["email"] = clean_email(sent["adminemail"])
            if row(conn, "SELECT 1 AS x FROM users WHERE email = :e AND recordid <> :u", e=admin["email"], u=a["primaryuserid"]):
                raise HTTPException(409, f"{admin['email']} already has a login")
        if admin:
            sets = ", ".join(f"{k} = :{k}" for k in admin)
            run(conn, f"UPDATE users SET {sets}, updated = :now WHERE recordid = :u", now=utcnow(), u=a["primaryuserid"], **admin)
    _audit(conn, user, "admin-update-account", "account", accountid, {**fields, **{f"admin{k}": v for k, v in admin.items()}}, request)
    return {"ok": True}


@router.post("/accounts/{accountid}/launch")
def launch_account(accountid: str, request: Request, user: dict = Depends(platform_viewer), conn: Connection = Depends(get_conn)):
    """A short session in this customer's portal for the signed-in staff member (read-only for
    support staff). Logged here, and everything done with it is logged under the staff member."""
    a = row(conn, "SELECT name FROM accounts WHERE recordid = :id AND platform = 0 AND deleted IS NULL", id=accountid)
    if not a:
        raise HTTPException(404, "Account not found")
    _audit(conn, user, "admin-launch-account", "account", accountid, {"name": a["name"]}, request)
    log(conn, user, "staff-launch", "account", accountid, {"staff": user["email"]}, accountid=accountid,
        ip=client_ip(request))
    return {"token": issue_launch_token(user["recordid"], accountid), "minutes": LAUNCH_MINUTES}


# ------------------------------------------------------------------------------------------------
# Users
# ------------------------------------------------------------------------------------------------

class UserIn(BaseModel):
    accountid: str
    email: str
    name: str
    role: str = "staff"
    platformrole: str | None = None
    timezone: str | None = None          # None/"" = the account's time zone


class UserPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    platformrole: str | None = None      # "" clears it
    disabled: bool | None = None
    timezone: str | None = None          # "" = back to the account's time zone


def _create_user(conn, accountid, email, name, role, platformrole, timezone=None) -> dict:
    """A login with no usable password: it can't sign in until its invitation link is used."""
    email = clean_email(email)
    if row(conn, "SELECT 1 AS x FROM users WHERE email = :e", e=email):
        raise HTTPException(409, f"{email} already has a login")
    if role not in ("owner", "admin", "staff", "auditor"):
        raise HTTPException(400, "Unknown role")
    if platformrole not in (None, "superadmin", "support"):
        raise HTTPException(400, "Unknown platform role")
    uid = newid()
    run(conn, """INSERT INTO users (recordid, accountid, email, name, passwordhash, role, platformrole, timezone)
                 VALUES (:id, :a, :e, :n, :p, :r, :pr, :tz)""",
        id=uid, a=accountid, e=email, n=name, p=hash_password(secrets.token_urlsafe(32)), r=role, pr=platformrole,
        tz=clean_timezone(timezone))
    return {"recordid": uid, "email": email}


def _invite(conn, background: BackgroundTasks, userid: str, purpose: str, by: dict) -> dict:
    """Issue a link and email it after the response. Without SMTP the link comes back for the admin
    to pass on by hand - the only time a link is ever shown."""
    target = row(conn, """SELECT u.email, u.name, u.role, u.platformrole, a.name AS accountname, a.platform,
                                 COALESCE(u.timezone, a.timezone) AS tz
                          FROM users u JOIN accounts a ON a.recordid = u.accountid WHERE u.recordid = :u""", u=userid)
    link = invitations.issue(conn, userid, purpose, by["recordid"])
    if invitations.email_configured():
        background.add_task(invitations.deliver, purpose=purpose, name=target["name"], email=target["email"], link=link,
                            expires=invitations.expiry(purpose), accountname=target["accountname"],
                            staff=bool(target["platform"]),
                            role=target["platformrole"] if target["platform"] else target["role"],
                            invitedby=by.get("name"), tz=target["tz"])
        return {"email": target["email"], "emailed": True}
    return {"email": target["email"], "emailed": False, "link": link}


@router.get("/email-preview/{name}")
def email_preview(name: str, user: dict = Depends(platform_viewer)):
    """How an email looks, with sample data - for checking the design in a browser. Sends nothing."""
    samples = {"invitation": emails.sample_invitation}
    if name not in samples:
        raise HTTPException(404, "Unknown email")
    subject, html, text = samples[name]()
    return HTMLResponse(emails.for_browser(html), headers={"X-Email-Subject": subject.encode("ascii", "replace").decode()})


# Sortable columns of the staff grid → the SQL they sort by.
USER_SORTS = {"name": "u.name", "email": "u.email", "role": "u.platformrole", "lastlogin": "u.lastlogin",
              "status": "u.deleted IS NOT NULL", "added": "u.added"}


@router.get("/users")
def list_users(q: str | None = None, role: str | None = None, status: str | None = None,
               sort: str = "name", dir: str = "asc", page: int = 1, pagesize: int = 25,
               user: dict = Depends(platform_viewer), conn: Connection = Depends(get_conn)):
    """TripProof staff logins, one page at a time. Customers manage their own users; those are seen
    (read-only) on the customer's page, never here.

    Filters: q (name, email), role = superadmin | support | none (no admin access), status = active |
    invited (never set a password) | disabled."""
    pagesize = max(1, min(pagesize, 1000))
    page = max(page, 1)
    direction = "DESC" if dir.lower() == "desc" else "ASC"
    order_by = f"{USER_SORTS.get(sort, 'u.name')} {direction}, u.name ASC, u.recordid ASC"
    passwordset = "EXISTS (SELECT 1 FROM activitylog l WHERE l.userid = u.recordid AND l.action IN ('password-set', 'login'))"
    where = ["a.platform = 1", "(:q IS NULL OR CONCAT_WS(' ', u.email, u.name) LIKE CONCAT('%', :q, '%'))"]
    params = {"q": q or None}
    if role in ("superadmin", "support"):
        where.append("u.platformrole = :role"); params["role"] = role
    elif role == "none":
        where.append("u.platformrole IS NULL")
    if status == "active":
        where.append(f"u.deleted IS NULL AND {passwordset}")
    elif status == "invited":
        where.append(f"u.deleted IS NULL AND NOT {passwordset}")
    elif status == "disabled":
        where.append("u.deleted IS NOT NULL")
    clause = " AND ".join(where)
    base = "FROM users u JOIN accounts a ON a.recordid = u.accountid"
    total = row(conn, f"SELECT COUNT(*) AS n {base} WHERE {clause}", **params)["n"]
    items = rows(conn, f"""
        SELECT u.recordid, u.email, u.name, u.platformrole, u.timezone, u.lastlogin, u.added, u.deleted,
               {passwordset} AS passwordset,
               (SELECT MAX(t.added) FROM passwordtokens t WHERE t.userid = u.recordid) AS lastinvited
        {base} WHERE {clause} ORDER BY {order_by} LIMIT :lim OFFSET :off
    """, lim=pagesize, off=(page - 1) * pagesize, **params)
    staff = row(conn, "SELECT recordid FROM accounts WHERE platform = 1 LIMIT 1")
    return {"total": total, "page": page, "pagesize": pagesize, "items": items,
            "staffaccountid": staff["recordid"] if staff else None}


@router.post("/users")
def create_user(body: UserIn, request: Request, background: BackgroundTasks, user: dict = Depends(platform_admin),
                conn: Connection = Depends(get_conn)):
    a = row(conn, "SELECT platform FROM accounts WHERE recordid = :id AND deleted IS NULL", id=body.accountid)
    if not a:
        raise HTTPException(404, "Account not found")
    if body.platformrole and not a["platform"]:
        raise HTTPException(400, "Platform roles are only for TripProof staff accounts")
    result = _create_user(conn, body.accountid, body.email, body.name, body.role, body.platformrole,
                          body.timezone or ("America/New_York" if a["platform"] else None))
    result["invitation"] = _invite(conn, background, result["recordid"], "invite", user)
    _audit(conn, user, "admin-create-user", "user", result["recordid"], {"email": result["email"], "role": body.role,
                                                                          "platformrole": body.platformrole}, request)
    return result


@router.patch("/users/{userid}")
def patch_user(userid: str, body: UserPatch, request: Request, user: dict = Depends(platform_admin),
               conn: Connection = Depends(get_conn)):
    target = row(conn, """SELECT u.recordid, u.platformrole, a.platform FROM users u JOIN accounts a ON a.recordid = u.accountid
                          WHERE u.recordid = :id""", id=userid)
    if not target:
        raise HTTPException(404, "User not found")
    if userid == user["recordid"] and (body.disabled or body.platformrole == ""):
        raise HTTPException(400, "You cannot disable yourself or remove your own admin access")
    fields = {}
    if body.name:
        fields["name"] = body.name
    if body.role:
        if body.role not in ("owner", "admin", "staff", "auditor"):
            raise HTTPException(400, "Unknown role")
        fields["role"] = body.role
    if body.platformrole is not None:
        if body.platformrole and not target["platform"]:
            raise HTTPException(400, "Platform roles are only for TripProof staff accounts")
        if body.platformrole not in ("", "superadmin", "support"):
            raise HTTPException(400, "Unknown platform role")
        fields["platformrole"] = body.platformrole or None
    if body.disabled is not None:
        fields["deleted"] = utcnow() if body.disabled else None
    if body.timezone is not None:
        fields["timezone"] = clean_timezone(body.timezone)
    if fields:
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        run(conn, f"UPDATE users SET {sets}, updated = :now WHERE recordid = :id", now=utcnow(), id=userid, **fields)
    _audit(conn, user, "admin-update-user", "user", userid, body.model_dump(exclude_none=True), request)
    return {"ok": True}


@router.post("/users/{userid}/invite")
def send_invitation(userid: str, request: Request, background: BackgroundTasks, user: dict = Depends(platform_admin),
                    conn: Connection = Depends(get_conn)):
    """Email a link to set a new password. A login that has never set one gets an invitation; one that
    has gets a reset. The current password keeps working until the link is used."""
    u = row(conn, "SELECT recordid FROM users WHERE recordid = :id AND deleted IS NULL", id=userid)
    if not u:
        raise HTTPException(404, "User not found")
    has_password = row(conn, "SELECT 1 AS x FROM activitylog WHERE userid = :u AND action IN ('password-set', 'login') LIMIT 1", u=userid)
    purpose = "reset" if has_password else "invite"
    result = _invite(conn, background, userid, purpose, user)
    _audit(conn, user, "admin-send-invitation", "user", userid, {"purpose": purpose, "emailed": result["emailed"]}, request)
    return result


# ------------------------------------------------------------------------------------------------
# Subscription plans (fleet-size tiers)
# ------------------------------------------------------------------------------------------------

class PlanIn(BaseModel):
    code: str
    name: str
    description: str | None = None
    minvehicles: int
    maxvehicles: int | None = None
    monthlyprice: float | None = None       # None = "contact us", not sold online
    trialdays: int = 0
    features: list[str] = []
    active: bool = True
    sortorder: int = 0


def _check_plan(conn, body: PlanIn, planid: str | None = None) -> dict:
    if body.minvehicles < 1 or (body.maxvehicles is not None and body.maxvehicles < body.minvehicles):
        raise HTTPException(400, "The vehicle range must start at 1 or more and end at or after it starts")
    if body.monthlyprice is not None and body.monthlyprice < 0:
        raise HTTPException(400, "Price can't be negative")
    if not 0 <= body.trialdays <= 90:
        raise HTTPException(400, "Trial must be 0-90 days")
    if not body.name.strip():
        raise HTTPException(400, "Name the plan")
    plans.check_no_overlap(conn, body.minvehicles, body.maxvehicles, body.active, planid)
    return {"code": body.code.strip().upper().replace(" ", "_"), "name": body.name.strip(), "description": body.description,
            "minv": body.minvehicles, "maxv": body.maxvehicles,
            "price": round(body.monthlyprice, 2) if body.monthlyprice is not None else None, "trial": body.trialdays,
            "features": json.dumps([f.strip() for f in body.features if f.strip()]), "active": 1 if body.active else 0,
            "sort": body.sortorder}


@router.get("/plans")
def list_plans(user: dict = Depends(platform_viewer), conn: Connection = Depends(get_conn)):
    items = rows(conn, """
        SELECT pl.*, (SELECT COUNT(*) FROM subscriptions s WHERE s.planid = pl.recordid AND s.canceledon IS NULL) AS subscribers,
               (SELECT COUNT(*) FROM accounts a WHERE a.planid = pl.recordid AND a.status = 'setup') AS applying
        FROM plans pl ORDER BY pl.sortorder, pl.minvehicles
    """)
    for p in items:
        p["features"] = json.loads(p["features"]) if p["features"] else []
    return items


@router.post("/plans")
def create_plan(body: PlanIn, request: Request, user: dict = Depends(platform_admin), conn: Connection = Depends(get_conn)):
    v = _check_plan(conn, body)
    if row(conn, "SELECT 1 AS x FROM plans WHERE code = :c", c=v["code"]):
        raise HTTPException(409, "A plan with that code exists")
    pid = newid()
    run(conn, """INSERT INTO plans (recordid, code, name, description, minvehicles, maxvehicles, monthlyprice, trialdays, features, active, sortorder)
                 VALUES (:id, :code, :name, :description, :minv, :maxv, :price, :trial, :features, :active, :sort)""", id=pid, **v)
    _audit(conn, user, "admin-create-plan", "plan", pid, {"code": v["code"], "price": v["price"]}, request)
    return {"recordid": pid}


@router.put("/plans/{planid}")
def update_plan(planid: str, body: PlanIn, request: Request, user: dict = Depends(platform_admin),
                conn: Connection = Depends(get_conn)):
    """The code is fixed once created. A new price applies to new subscriptions; existing
    subscribers keep the price they signed up at (a new Stripe price is made on next use)."""
    old = row(conn, "SELECT code, monthlyprice FROM plans WHERE recordid = :id", id=planid)
    if not old:
        raise HTTPException(404, "Plan not found")
    v = _check_plan(conn, body, planid)
    v.pop("code")
    run(conn, """UPDATE plans SET name = :name, description = :description, minvehicles = :minv, maxvehicles = :maxv,
                    monthlyprice = :price, trialdays = :trial, features = :features, active = :active, sortorder = :sort,
                    updated = UTC_TIMESTAMP() WHERE recordid = :id""", id=planid, **v)
    _audit(conn, user, "admin-update-plan", "plan", planid, {"code": old["code"], "oldprice": old["monthlyprice"],
                                                             "price": v["price"]}, request)
    return {"ok": True}


# ------------------------------------------------------------------------------------------------
# Fee schedule (screening services TripProof orders for customers)
# ------------------------------------------------------------------------------------------------

class FeeIn(BaseModel):
    code: str
    name: str
    price: float | None = None           # None = not set
    # What this buys, in our words, for whoever is choosing it; and what the vendor is asked for,
    # in theirs. Only the screening tiers use either - see migration 287.
    covers: str | None = None
    products: str | None = None
    active: bool = True
    sortorder: int = 0


def _check_fee(body: FeeIn) -> dict:
    code = (body.code or "").strip().upper()
    name = (body.name or "").strip()
    if not code or not name:
        raise HTTPException(400, "Code and name are required")
    if body.price is not None and body.price < 0:
        raise HTTPException(400, "Price can't be negative")
    return {"code": code, "name": name, "price": round(body.price, 2) if body.price is not None else None,
            "covers": (body.covers or "").strip() or None,
            # Their codes, their case. Upper-casing them would be us deciding how another company
            # spells its own product names.
            "products": ", ".join(x.strip() for x in (body.products or "").split(",") if x.strip())
                        or None,
            "active": 1 if body.active else 0, "sortorder": body.sortorder}


@router.get("/fees")
def list_fees(user: dict = Depends(platform_viewer), conn: Connection = Depends(get_conn)):
    return rows(conn, "SELECT recordid, code, name, covers, products, price, active, "
                      "sortorder, updated FROM feeschedule ORDER BY sortorder, name")


@router.post("/fees")
def create_fee(body: FeeIn, request: Request, user: dict = Depends(platform_admin), conn: Connection = Depends(get_conn)):
    v = _check_fee(body)
    if row(conn, "SELECT 1 AS x FROM feeschedule WHERE code = :code", code=v["code"]):
        raise HTTPException(409, f"A fee with code {v['code']} already exists")
    fid = newid()
    run(conn, """INSERT INTO feeschedule (recordid, code, name, covers, products, price, active,
                                       sortorder)
                 VALUES (:id, :code, :name, :covers, :products, :price, :active, :sortorder)""",
        id=fid, **v)
    _audit(conn, user, "admin-create-fee", "fee", fid, v, request)
    return {"recordid": fid}


@router.put("/fees/{feeid}")
def update_fee(feeid: str, body: FeeIn, request: Request, user: dict = Depends(platform_admin),
               conn: Connection = Depends(get_conn)):
    old = row(conn, "SELECT code, price FROM feeschedule WHERE recordid = :id", id=feeid)
    if not old:
        raise HTTPException(404, "Fee not found")
    v = _check_fee(body)
    v.pop("code")                        # the code is fixed once created
    run(conn, """UPDATE feeschedule SET name = :name, covers = :covers, products = :products,
                    price = :price, active = :active, sortorder = :sortorder,
                    updated = UTC_TIMESTAMP() WHERE recordid = :id""", id=feeid, **v)
    _audit(conn, user, "admin-update-fee", "fee", feeid, {"code": old["code"], "oldprice": old["price"], "price": v["price"]}, request)
    return {"ok": True}


# ------------------------------------------------------------------------------------------------
# Brokers
# ------------------------------------------------------------------------------------------------

class PayerIn(BaseModel):
    code: str
    name: str
    # medicaid | medicare_advantage | commercial | workers_comp | auto_pip | va | facility
    # | broker. See rates.CATEGORIES.
    category: str = "broker"
    # How the clearinghouse names this payer, where it is billed electronically at all.
    payerid: str | None = None
    website: str | None = None
    notes: str | None = None
    active: bool = True
    # Where the broker is. The writer is shared with the company screen and treats a field it is
    # not given as blank, so leaving these off this model erased them on every save.
    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    phone: str | None = None
    fax: str | None = None
    contactname: str | None = None
    contactemail: str | None = None


@router.get("/brokers")
def list_payers(user: dict = Depends(platform_viewer), conn: Connection = Depends(get_conn)):
    """The shared list - the brokers TripProof publishes compliance rules against.

    NOT a company's payers. Those belong to the company, are managed on its own Payers
    screen, and are invisible here. These are shared because a broker's requirements are
    checked against trips carried for it, which only works while every company points at the
    same row.
    """
    return {
        "categories": rateset.CATEGORIES,
        "payers": rows(conn, """
            SELECT b.*,
                   (SELECT COUNT(*) FROM rulesets r WHERE r.brokerid = b.recordid) AS rulesets,
                   (SELECT GROUP_CONCAT(DISTINCT r.state ORDER BY r.state)
                      FROM rulesets r WHERE r.brokerid = b.recordid) AS states,
                   (SELECT COUNT(*) FROM trips t WHERE t.brokerid = b.recordid) AS trips,
                   (SELECT COUNT(DISTINCT c.scheduleid) FROM companycontracts c
                     WHERE c.payerid = b.recordid AND c.scheduleid IS NOT NULL) AS schedules
            FROM payers b WHERE b.accountid IS NULL ORDER BY b.category, b.name
        """),
    }


@router.post("/brokers")
def create_payer(body: PayerIn, request: Request, user: dict = Depends(platform_admin),
                 conn: Connection = Depends(get_conn)):
    if body.category not in rateset.CATEGORIES:
        raise HTTPException(400, f"Unknown payer category {body.category}")
    if row(conn, "SELECT 1 AS x FROM payers WHERE accountid IS NULL AND code = :c",
           c=body.code.upper()):
        raise HTTPException(409, "A payer with that code exists")
    # The same writer the company screen uses, with no account on it - which is what makes a
    # payer shared. One implementation, so a field added to one is added to both.
    bid = rateset.save_payer(conn, None, body.model_dump())
    _audit(conn, user, "admin-create-payer", "payer", bid, body.model_dump(), request)
    return {"recordid": bid}


@router.put("/brokers/{payerrecordid}")
def update_payer(payerrecordid: str, body: PayerIn, request: Request,
                 user: dict = Depends(platform_admin), conn: Connection = Depends(get_conn)):
    if body.category not in rateset.CATEGORIES:
        raise HTTPException(400, f"Unknown payer category {body.category}")
    if not row(conn, "SELECT 1 AS x FROM payers WHERE recordid = :i AND accountid IS NULL",
               i=payerrecordid):
        raise HTTPException(404, "Payer not found")
    rateset.save_payer(conn, None, body.model_dump(), payerrecordid)
    _audit(conn, user, "admin-update-payer", "payer", payerrecordid, body.model_dump(), request)
    return {"ok": True}


# ------------------------------------------------------------------------------------------------
# Credential types
# ------------------------------------------------------------------------------------------------

class CredentialTypeIn(BaseModel):
    code: str
    name: str
    subject: str
    category: str | None = None
    maxagedays: int | None = None
    defaultvaliddays: int | None = None
    hasamount: bool = False
    description: str | None = None
    active: bool = True




@router.get("/credentialtypes")
def list_types(user: dict = Depends(platform_viewer), conn: Connection = Depends(get_conn)):
    return rows(conn, """
        SELECT t.*,
               (SELECT COUNT(*) FROM credentials c WHERE c.credentialtypeid = t.recordid AND c.deleted IS NULL) AS credentials,
               (SELECT COUNT(*) FROM requirements q WHERE q.credentialtypeid = t.recordid) AS requirements
        FROM credentialtypes t
        ORDER BY t.subject, t.category, t.name
    """)


def _check_type(body: CredentialTypeIn):
    if body.subject not in ("driver", "vehicle", "company"):
        raise HTTPException(400, "Subject must be driver, vehicle or company")
    for f in ("maxagedays", "defaultvaliddays"):
        v = getattr(body, f)
        if v is not None and v <= 0:
            raise HTTPException(400, f"{f} must be positive")


@router.post("/credentialtypes")
def create_type(body: CredentialTypeIn, request: Request, user: dict = Depends(platform_admin),
                conn: Connection = Depends(get_conn)):
    _check_type(body)
    code = body.code.strip().upper().replace(" ", "_")
    if row(conn, "SELECT 1 AS x FROM credentialtypes WHERE code = :c", c=code):
        raise HTTPException(409, "A credential type with that code exists")
    tid = newid()
    run(conn, """
        INSERT INTO credentialtypes (recordid, code, name, subject, category, maxagedays, defaultvaliddays, hasamount,
                                     description, active)
        VALUES (:id, :c, :n, :s, :cat, :m, :dv, :ha, :d, :a)
    """, id=tid, c=code, n=body.name, s=body.subject, cat=body.category, m=body.maxagedays, dv=body.defaultvaliddays,
        ha=1 if body.hasamount else 0, d=body.description, a=1 if body.active else 0)
    _audit(conn, user, "admin-create-credentialtype", "credentialtype", tid, body.model_dump(), request)
    return {"recordid": tid}


@router.put("/credentialtypes/{typeid}")
def update_type(typeid: str, body: CredentialTypeIn, request: Request, user: dict = Depends(platform_admin),
                conn: Connection = Depends(get_conn)):
    """Code and subject are fixed once created - credentials and requirements depend on them.
    Changing an age limit changes how every published rule using the type evaluates."""
    _check_type(body)
    t = row(conn, "SELECT subject FROM credentialtypes WHERE recordid = :id", id=typeid)
    if not t:
        raise HTTPException(404, "Credential type not found")
    if t["subject"] != body.subject:
        raise HTTPException(400, "A credential type's subject cannot change")
    run(conn, """
        UPDATE credentialtypes SET name = :n, category = :cat, maxagedays = :m, defaultvaliddays = :dv, hasamount = :ha,
               description = :d, active = :a, updated = :now
        WHERE recordid = :id
    """, n=body.name, cat=body.category, m=body.maxagedays, dv=body.defaultvaliddays, ha=1 if body.hasamount else 0,
        d=body.description, a=1 if body.active else 0, now=utcnow(), id=typeid)
    _audit(conn, user, "admin-update-credentialtype", "credentialtype", typeid, body.model_dump(), request)
    return {"ok": True}


# ------------------------------------------------------------------------------------------------
# Activity log (platform-wide)
# ------------------------------------------------------------------------------------------------

@router.get("/activity")
def activity(accountid: str | None = None, userid: str | None = None, action: str | None = None, phi: bool | None = None,
             datefrom: date | None = None, dateto: date | None = None, q: str | None = None,
             page: int = 1, pagesize: int = 100,
             user: dict = Depends(platform_viewer), conn: Connection = Depends(get_conn)):
    pagesize = max(1, min(pagesize, 500))
    where, params = ["1 = 1"], {}
    if accountid:
        where.append("l.accountid = :acct"); params["acct"] = accountid
    if userid:
        # Everything done by that login, in any account (staff actions in a launched portal included).
        where.append("l.userid = :uid"); params["uid"] = userid
    if action:
        where.append("l.action = :action"); params["action"] = action
    if phi is not None:
        where.append("l.phi = :phi"); params["phi"] = 1 if phi else 0
    if datefrom:
        where.append("l.added >= :df"); params["df"] = datefrom
    if dateto:
        where.append("l.added < :dt"); params["dt"] = dateto + timedelta(days=1)
    if q:
        where.append("CONCAT_WS(' ', u.email, u.name, l.entitytype, l.entityid, l.ip) LIKE CONCAT('%', :q, '%')"); params["q"] = q
    clause = " AND ".join(where)
    total = row(conn, f"SELECT COUNT(*) AS n FROM activitylog l LEFT JOIN users u ON u.recordid = l.userid WHERE {clause}", **params)["n"]
    items = rows(conn, f"""
        SELECT l.recordid, l.added, l.action, l.entitytype, l.entityid, l.phi, l.detail, l.ip,
               u.name AS username, u.email, a.name AS accountname
        FROM activitylog l LEFT JOIN users u ON u.recordid = l.userid LEFT JOIN accounts a ON a.recordid = l.accountid
        WHERE {clause} ORDER BY l.added DESC LIMIT :lim OFFSET :off
    """, lim=pagesize, off=(max(page, 1) - 1) * pagesize, **params)
    actions = [r["action"] for r in rows(conn, "SELECT DISTINCT action FROM activitylog ORDER BY action")]
    return {"total": total, "page": page, "pagesize": pagesize, "items": items, "actions": actions}


# -------------------------------------------------------------------------------------------
# Payment gateways - which processors TripProof offers its customers.
#
# The platform decides what is on the menu. It does NOT touch anybody's keys: there is no
# endpoint here that reads a customer's credentials, and that is on purpose. Support can see
# that a company is configured and which processor it picked; the key itself is the company's,
# and staff standing in their office is not the same as staff being them.
# -------------------------------------------------------------------------------------------

class GatewayIn(BaseModel):
    active: bool = True
    note: str | None = None


@router.get("/gateways")
def gateway_catalog(user: dict = Depends(platform_viewer), conn: Connection = Depends(get_conn)):
    """Every adapter, whether it is offered, and how many companies are on each."""
    counts = {r["gatewaycode"]: r for r in rows(conn, """
        SELECT gatewaycode, COUNT(*) AS configured,
               SUM(active) AS inuse
        FROM accountgateways GROUP BY gatewaycode
    """)}
    out = []
    for g in gateways.catalog(conn):
        c = counts.get(g["code"]) or {}
        out.append({**g, "configured": int(c.get("configured") or 0),
                    "inuse": int(c.get("inuse") or 0)})
    return {"gateways": out}


@router.put("/gateways/{code}")
def set_gateway(code: str, body: GatewayIn, request: Request,
                user: dict = Depends(platform_admin), conn: Connection = Depends(get_conn)):
    """Offer an adapter, or withdraw it."""
    if code not in gateways.ADAPTERS:
        raise HTTPException(404, "No such payment gateway")
    # Withdrawing one that companies are actively taking money through would stop those
    # payments, so it is refused rather than done quietly.
    if not body.active:
        inuse = row(conn, """
            SELECT COUNT(*) AS n FROM accountgateways
            WHERE gatewaycode = :c AND active = 1
        """, c=code)["n"]
        if inuse:
            raise HTTPException(409, f"{gateways.describe(code)} is in use by {inuse} "
                                     "company(s). They have to move off it first.")
    gateways.set_offered(conn, code, body.active, body.note)
    _audit(conn, user, "gateway-offered" if body.active else "gateway-withdrawn",
           "platform", None, {"gateway": code}, request)
    return {"ok": True}


# ------------------------------------------------------------------------------------------------
# Legal review of the rules. A rule is a draft until somebody qualified signs it off as a correct
# statement of what the law, program or contract requires - and only an approved rule may ever be
# enforced against a trip. Each decision is stamped and kept as a new version of the rule.
# ------------------------------------------------------------------------------------------------
REVIEW_STATES = ("draft", "reviewed", "approved", "retired")


RULE_SORTS = {
    "code": "r.qualificationcode", "qualification": "q.name", "state": "r.jurisdiction", "category": "r.authoritycategory",
    "source": "CONCAT_WS(' ', r.authority, r.citation)", "version": "version",
    "reviewed": "r.legalreviewedon", "status": "FIELD(r.legalreview, 'draft', 'reviewed', 'approved', 'retired')",
}
CATEGORIES = ("FEDERAL_GENERAL", "STATE_GENERAL", "FEDERAL_MEDICAID", "STATE_MEDICAID",
              "CONTRACT_COMPANY")


@router.get("/rules")
def rules_for_review(q: str | None = None, status: str | None = None, category: str | None = None,
                     state: str | None = None, sort: str = "code", dir: str = "asc", page: int = 1,
                     pagesize: int = 25, user: dict = Depends(platform_viewer),
                     conn: Connection = Depends(get_conn)):
    """One page of the platform's driver rules, filtered and sorted, with the count in each review
    state across all of them. Search reads the qualification, its code, the authority and the
    citation."""
    pagesize = max(1, min(pagesize, 1000))
    page = max(page, 1)
    direction = "DESC" if dir.lower() == "desc" else "ASC"
    order_by = f"{RULE_SORTS.get(sort, 'r.qualificationcode')} {direction}, q.sortorder, r.code"
    base = "r.subject = 'driver' AND r.accountid IS NULL AND r.effectiveto IS NULL"
    where = [base, "(:q IS NULL OR CONCAT_WS(' ', q.name, r.qualificationcode, r.authority, "
                   "r.citation, r.code) LIKE CONCAT('%', :q, '%'))"]
    params = {"q": q or None}
    if status in REVIEW_STATES:
        where.append("r.legalreview = :status"); params["status"] = status
    if category in CATEGORIES:
        where.append("r.authoritycategory = :category"); params["category"] = category
    if state:
        where.append("r.jurisdiction = :state"); params["state"] = state.upper()[:2]
    clause = " AND ".join(where)
    joins = "FROM compliancerules r LEFT JOIN qualificationcatalog q ON q.code = r.qualificationcode"
    total = row(conn, f"SELECT COUNT(*) AS n {joins} WHERE {clause}", **params)["n"]
    items = rows(conn, f"""
        SELECT r.code, r.qualificationcode, q.name AS qualification, r.authoritycategory,
               r.authority, r.citation, r.sourceurl, r.jurisdiction, r.enforcement, r.legalreview,
               r.legalreviewedon,
               u.name AS legalreviewedby,
               (SELECT MAX(v.version) FROM compliancerulesversions v
                WHERE v.rulecode = r.code AND v.accountid IS NULL) AS version
        {joins} LEFT JOIN users u ON u.recordid = r.legalreviewedby
        WHERE {clause}
        ORDER BY {order_by}
        LIMIT :lim OFFSET :off
    """, lim=pagesize, off=(page - 1) * pagesize, **params)
    from app import citations
    for r in items:
        # Each part of the citation with the page it can be read on, so a reviewer checks the
        # rule against the text it cites without hunting for it.
        r["links"] = citations.links(r["citation"], r["sourceurl"])
    counts = {r["legalreview"]: r["n"] for r in rows(conn, f"""
        SELECT r.legalreview, COUNT(*) AS n FROM compliancerules r WHERE {base} GROUP BY r.legalreview
    """)}
    jurisdictions = [r["jurisdiction"] for r in rows(conn, f"""
        SELECT DISTINCT r.jurisdiction FROM compliancerules r
        WHERE {base} AND r.jurisdiction IS NOT NULL ORDER BY r.jurisdiction
    """)]
    return {"total": total, "page": page, "pagesize": pagesize, "items": items,
            "counts": counts, "states": list(REVIEW_STATES), "jurisdictions": jurisdictions}


class RuleReviewIn(BaseModel):
    legalreview: str


@router.put("/rules/{code}/review")
def review_rule(code: str, body: RuleReviewIn, request: Request,
                user: dict = Depends(platform_admin), conn: Connection = Depends(get_conn)):
    if body.legalreview not in REVIEW_STATES:
        raise HTTPException(400, "Unknown review state")
    n = run(conn, """
        UPDATE compliancerules SET legalreview = :s, legalreviewedby = :u, legalreviewedon = :now
        WHERE code = :c AND subject = 'driver' AND accountid IS NULL AND effectiveto IS NULL
    """, s=body.legalreview, u=user["recordid"], now=utcnow(), c=code).rowcount
    if not n:
        raise HTTPException(404, "No such rule")
    from app import ruleversions
    ruleversions.capture(conn, userid=user["recordid"], reason=f"review: {body.legalreview}")
    log(conn, user, "rule-review", "compliancerule", code, {"legalreview": body.legalreview},
        ip=client_ip(request))
    conn.commit()
    return {"ok": True}
