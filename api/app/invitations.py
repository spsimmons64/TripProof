###################################################################################################
# Password invitations - the only way a password gets set by someone other than its owner.
#
# issue() mints a random token, stores only its SHA-256, retires the user's older unused links and
# returns the link. deliver() emails it (run as a background task, after the response) using the
# design in app/emails.py. The link is
# spent the first time it sets a password.
#
#   invite   a new login: "You've been invited to TripProof"      - good for 7 days
#   reset    an admin-triggered reset of an existing login          - good for 72 hours
###################################################################################################
import hashlib
import secrets
from datetime import timedelta

from sqlalchemy.engine import Connection

from app import emails, mailer
from app.config import settings
from app.db import newid, row, run, utcnow

LIFETIME = {"invite": timedelta(days=7), "reset": timedelta(hours=72)}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def email_configured() -> bool:
    return mailer.configured()


def issue(conn: Connection, userid: str, purpose: str, createdby: str | None) -> str:
    token = secrets.token_urlsafe(32)
    now = utcnow()
    # Only the newest link works: retire anything still outstanding for this user.
    run(conn, "UPDATE passwordtokens SET usedon = :now WHERE userid = :u AND usedon IS NULL", now=now, u=userid)
    run(conn, """
        INSERT INTO passwordtokens (recordid, userid, tokenhash, purpose, expires, createdby)
        VALUES (:id, :u, :h, :p, :exp, :by)
    """, id=newid(), u=userid, h=hash_token(token), p=purpose, exp=now + LIFETIME[purpose], by=createdby)
    return f"{settings.public_url.rstrip('/')}/reset?token={token}"


def issue_for_driver(conn: Connection, driverid: str, purpose: str,
                     createdby: str | None) -> str:
    """The same invitation, against a driver record rather than a user record.

    The link goes to the driver's app, not to the office sign-in: a driver sent to /reset ends up
    at a screen built for a dispatcher, which is the sort of thing that gets a product rung about
    on a Monday morning."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    run(conn, "UPDATE passwordtokens SET usedon = :now WHERE driverid = :d AND usedon IS NULL",
        now=now, d=driverid)
    run(conn, """
        INSERT INTO passwordtokens (recordid, driverid, tokenhash, purpose, expires, createdby)
        VALUES (:id, :d, :h, :p, :exp, :by)
    """, id=newid(), d=driverid, h=hash_token(token), p=purpose,
        exp=now + LIFETIME[purpose], by=createdby)
    return f"{settings.public_url.rstrip('/')}/drive/password?token={token}"


def lookup(conn: Connection, token: str) -> dict | None:
    """The live token row joined to its user, or None if unknown, spent, expired, or the login is gone."""
    return row(conn, """
        SELECT t.recordid, t.purpose, t.expires, u.recordid AS userid, u.email, u.name, a.name AS accountname
        FROM passwordtokens t
        JOIN users u ON u.recordid = t.userid
        JOIN accounts a ON a.recordid = u.accountid
        WHERE t.tokenhash = :h AND t.usedon IS NULL AND t.expires > :now
          AND u.deleted IS NULL AND a.deleted IS NULL AND (a.status IN ('active', 'setup') OR (a.status = 'inactive' AND a.holdreason = 'billing'))
    """, h=hash_token(token), now=utcnow())


def deliver(**invite):
    """Email an invitation or reset (see emails.invitation for the fields). Run as a background task;
    failures are logged, not raised - the admin can resend from the portal."""
    subject, html, text = emails.invitation(**invite)
    mailer.send(invite["email"], subject, html, text)


def expiry(purpose: str):
    return utcnow() + LIFETIME[purpose]
