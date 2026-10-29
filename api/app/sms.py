"""Text messages to drivers, through Twilio.

A driver is texted when the office gives them a trip, changes one they are on, takes them off one,
or cancels one. Only the trip's reference and its time go in the text: a text is not a secure
channel, so nothing about the passenger does. The details are in the app.

Queued with the change that causes it and sent after that change is committed, on its own thread,
so the office never waits on Twilio and a driver is never told about a change that was rolled back.
Every text is kept (drivertexts) with what Twilio said.
"""

import base64
import json
import logging
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from sqlalchemy.engine import Connection

from app.config import settings
from app.db import engine, newid, row, run, utcnow

log = logging.getLogger(__name__)
TIMEOUT = 15


def number(phone: str | None) -> str | None:
    """A US number as Twilio takes it: +1 and ten digits. None if it is not one."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return f"+1{digits}" if len(digits) == 10 else None


def when(at: datetime | None) -> str:
    return f"{at:%-I:%M %p} on {at:%m/%d}" if at else "will-call"


def tell(conn: Connection, accountid: str, driverid: str | None, kind: str, text: str,
         tripid: str | None = None, legid: str | None = None) -> None:
    """Queue a text to this driver; it goes once the change that caused it is committed."""
    if not driverid:
        return
    d = row(conn, "SELECT phone FROM drivers WHERE recordid = :d AND accountid = :a", d=driverid, a=accountid)
    to = number((d or {}).get("phone"))
    status = "queued" if settings.twilio_account_sid and to else ("nophone" if not to else "off")
    rid = newid()
    body = f"TripProof: {text}"[:480]
    run(conn, """
        INSERT INTO drivertexts (recordid, accountid, driverid, tripid, legid, kind, tonumber, body, status, added)
        VALUES (:id, :a, :d, :t, :l, :k, :to, :b, :s, :now)
    """, id=rid, a=accountid, d=driverid, t=tripid, l=legid, k=kind, to=to, b=body, s=status, now=utcnow())
    if status == "queued":
        conn.info.setdefault("after_commit", []).append(
            lambda: threading.Thread(target=_send, args=(rid, to, body), daemon=True).start())


def _send(rid: str, to: str, body: str) -> None:
    sid, token = settings.twilio_account_sid, settings.twilio_auth_token
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode({"To": to, "From": settings.twilio_from, "Body": body}).encode()
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    status, twiliosid, error = "failed", None, None
    try:
        req = urllib.request.Request(url, data=data, headers={"Authorization": f"Basic {auth}"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as answer:          # noqa: S310
            got = json.loads(answer.read().decode())
        twiliosid = got.get("sid")
        status = "sent" if not got.get("error_code") else "failed"
        error = got.get("error_message")
    except urllib.error.HTTPError as e:
        try:
            error = json.loads(e.read().decode()).get("message")
        except Exception:                                                     # noqa: BLE001
            error = str(e)
    except Exception as e:                                                    # noqa: BLE001
        error = str(e)
    if status == "failed":
        log.warning("text to %s failed: %s", to, error)
    with engine.begin() as conn:
        run(conn, "UPDATE drivertexts SET status = :s, twiliosid = :sid, error = :e, sent = :now WHERE recordid = :r",
            s=status, sid=twiliosid, e=(error or "")[:400] or None, now=utcnow(), r=rid)
