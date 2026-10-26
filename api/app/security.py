###################################################################################################
# Authentication - bcrypt password hashes, short-lived HS256 bearer tokens. The token carries only
# the user id; the user row (and so the accountid every query is scoped by) is re-read per request,
# so deleting a user or changing their role takes effect immediately.
###################################################################################################
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Connection

from app.config import settings
from app.db import get_conn, row, utcnow

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    # A stored hash that bcrypt cannot read is a failed sign-in, not a crashed one. It should not
    # happen - but a row edited by hand, truncated by a column change or written by an older
    # scheme would otherwise turn every attempt to sign in into a 500, which tells an attacker
    # that the address exists and tells the person it belongs to nothing at all.
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except (ValueError, TypeError):
        return False


LAUNCH_MINUTES = 60


def issue_token(userid: str) -> str:
    now = utcnow()
    return jwt.encode({"sub": userid, "iat": now, "exp": now + timedelta(minutes=settings.jwt_minutes)},
                      settings.jwt_secret, algorithm="HS256")


def renew_token(claims: dict) -> str:
    """The same sign-in, extended from now. A staff member inside a customer's portal stays
    inside that one portal - the account rides along - and keeps the shorter launch limit."""
    if claims.get("acct"):
        return issue_launch_token(claims["sub"], claims["acct"])
    return issue_token(claims["sub"])


def issue_launch_token(staffid: str, accountid: str) -> str:
    """A staff member's short session inside one customer's portal (see current_user)."""
    now = utcnow()
    return jwt.encode({"sub": staffid, "acct": accountid, "iat": now, "exp": now + timedelta(minutes=LAUNCH_MINUTES)},
                      settings.jwt_secret, algorithm="HS256")


# Accounts whose users may sign in: active ones, unfinished applications, and accounts on a billing
# hold (so they can reach the Billing page and pay - nothing else; see current_user).
SIGNIN_ALLOWED = "(a.status IN ('active', 'setup') OR (a.status = 'inactive' AND a.holdreason = 'billing'))"
HOLD_PATHS = ("/api/billing", "/api/auth/", "/api/apply/config", "/api/notifications")


def current_user(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                 conn: Connection = Depends(get_conn)) -> dict:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        claims = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    # usertimezone: how this person wants timestamps shown (their own zone, else the account's).
    # `timezone` stays the account's - business dates are computed in the operator's local time.
    user = row(conn, f"""
        SELECT u.recordid, u.accountid, u.email, u.name, u.role, u.platformrole,
               a.name AS accountname, a.timezone, a.state, a.platform, a.status AS accountstatus,
               COALESCE(u.timezone, a.timezone) AS usertimezone,
               (a.status = 'inactive') AS billinghold
        FROM users u JOIN accounts a ON a.recordid = u.accountid
        WHERE u.recordid = :id AND u.deleted IS NULL AND a.deleted IS NULL AND {SIGNIN_ALLOWED}
    """, id=claims["sub"])
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    user["billinghold"] = bool(user["billinghold"])
    if claims.get("acct"):
        user = _launched(conn, user, claims["acct"])
    elif user["billinghold"] and not request.url.path.startswith(HOLD_PATHS):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Your subscription has lapsed. Update your payment card on the Billing page to continue.")
    return user


def _launched(conn: Connection, staff: dict, accountid: str) -> dict:
    """A launched session: TripProof staff inside a customer's portal.

    Every query scopes by accountid, so swapping in the customer's account is all it takes for the
    portal to show their data. The user id stays the staff member's, so the activity log records who
    actually did each thing. Super admins act with admin rights; support staff are read-only
    (auditor). The staff member must still hold a platform role - revoking it ends the session."""
    if not staff.get("platformrole"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    acct = row(conn, """SELECT recordid, name, timezone, state, status FROM accounts
                        WHERE recordid = :id AND platform = 0 AND deleted IS NULL""", id=accountid)
    if not acct:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That customer no longer exists")
    return {**staff, "accountid": acct["recordid"], "accountname": acct["name"], "timezone": acct["timezone"],
            "state": acct["state"], "accountstatus": acct["status"], "platform": 0, "role": "admin" if staff["platformrole"] == "superadmin" else "auditor",
            "launched": True, "billinghold": False}


def require_role(*roles: str):
    def check(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed for your role")
        return user
    return check


# Roles that may change data. Auditors (read-only outside users) can view and export only.
editor = require_role("owner", "admin", "staff")
# Company profile and billing: the account's owner and admins only.
account_admin = require_role("owner", "admin")


def require_platform(*roles: str):
    """TripProof staff only (users.platformrole). With no roles given, any platform role passes."""
    def check(user: dict = Depends(current_user)) -> dict:
        # A launched session is confined to the customer's portal, even for a super admin.
        if not user.get("platformrole") or user.get("launched") or (roles and user["platformrole"] not in roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin portal access required")
        return user
    return check


# superadmin changes rules, customers and users; support can look but not change.
platform_viewer = require_platform()
platform_admin = require_platform("superadmin")


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)
