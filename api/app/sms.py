"""Text messages to drivers and the office, through Bandwidth (Twilio where Bandwidth is not set).

A driver with the TripProofDriver app on their phone is told by a notification on it instead
(app/push.py), and texted only if that cannot be done - no app, or a phone Firebase has forgotten.

A driver is texted when the office gives them a trip, changes one they are on, takes them off one,
or cancels one. Only the trip's reference and its time go in the text: a text is not a secure
channel, so nothing about the passenger does. The details are in the app.

Queued with the change that causes it and sent after that change is committed, on its own thread,
so the office never waits on Twilio and a driver is never told about a change that was rolled back.
Every text is kept (drivertexts) with what the provider said.
"""

import base64
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from sqlalchemy.engine import Connection

from app import push
from app.config import settings
from app.db import engine, newid, row, run, utcnow

log = logging.getLogger(__name__)
TIMEOUT = 15


def can_send() -> bool:
    return bool(settings.bandwidth_client_id or settings.twilio_account_sid)


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
    device = row(conn, """
        SELECT recordid, token FROM driverdevices
        WHERE accountid = :a AND driverid = :d AND ended IS NULL ORDER BY lastseen DESC LIMIT 1
    """, a=accountid, d=driverid) if push.can_push() else None
    if device:
        channel, status = "push", "queued"
    else:
        channel, status = "sms", ("queued" if can_send() and to else ("nophone" if not to else "off"))
    rid = newid()
    body = f"TripProof: {text}"[:480]
    run(conn, """
        INSERT INTO drivertexts (recordid, accountid, driverid, tripid, legid, kind, channel, tonumber, body, status, added)
        VALUES (:id, :a, :d, :t, :l, :k, :c, :to, :b, :s, :now)
    """, id=rid, a=accountid, d=driverid, t=tripid, l=legid, k=kind, c=channel, to=to, b=body, s=status, now=utcnow())
    if status != "queued":
        return
    if device:
        said = {"kind": kind, "legid": legid, "tripid": tripid}
        conn.info.setdefault("after_commit", []).append(
            lambda: threading.Thread(target=_notify, args=(rid, device, text[:470], said, to), daemon=True).start())
    else:
        conn.info.setdefault("after_commit", []).append(
            lambda: threading.Thread(target=_send, args=(rid, to, body), daemon=True).start())


def _notify(rid: str, device: dict, text: str, data: dict, to: str | None) -> None:
    """A notification to the driver's app; a text instead if Firebase will not take it."""
    status, name, error, gone = push.send(device["token"], text, data)
    with engine.begin() as conn:
        if gone:
            # The app is gone from that phone. Ended, so the next message goes straight to a text.
            run(conn, "UPDATE driverdevices SET ended = :now WHERE recordid = :r AND ended IS NULL",
                now=utcnow(), r=device["recordid"])
        if status == "sent":
            run(conn, "UPDATE drivertexts SET status = 'sent', twiliosid = :n, sent = :now WHERE recordid = :r",
                n=(name or "")[-64:] or None, now=utcnow(), r=rid)
            return
        log.warning("notification %s failed: %s", rid, error)
        if not (to and can_send()):
            run(conn, "UPDATE drivertexts SET status = 'failed', error = :e, sent = :now WHERE recordid = :r",
                e=(error or "")[:400] or None, now=utcnow(), r=rid)
            return
        run(conn, "UPDATE drivertexts SET channel = 'sms' WHERE recordid = :r", r=rid)
    _send(rid, to, f"TripProof: {text}"[:480])


def tell_user(conn: Connection, accountid: str, userid: str, kind: str, text: str,
              tripid: str | None = None, legid: str | None = None) -> None:
    """Queue a text to somebody in the office, at the mobile on their login."""
    u = row(conn, "SELECT mobile FROM users WHERE recordid = :u AND accountid = :a", u=userid, a=accountid)
    to = number((u or {}).get("mobile"))
    status = "queued" if can_send() and to else ("nophone" if not to else "off")
    rid = newid()
    body = f"TripProof: {text}"[:480]
    run(conn, """
        INSERT INTO drivertexts (recordid, accountid, userid, tripid, legid, kind, tonumber, body, status, added)
        VALUES (:id, :a, :u, :t, :l, :k, :to, :b, :s, :now)
    """, id=rid, a=accountid, u=userid, t=tripid, l=legid, k=kind, to=to, b=body, s=status, now=utcnow())
    if status == "queued":
        conn.info.setdefault("after_commit", []).append(
            lambda: threading.Thread(target=_send, args=(rid, to, body), daemon=True).start())


# A Bandwidth login token, kept until shortly before it runs out.
_token = {"value": None, "until": 0.0}


def _bandwidth_token() -> str:
    if _token["value"] and time.time() < _token["until"]:
        return _token["value"]
    auth = base64.b64encode(f"{settings.bandwidth_client_id}:{settings.bandwidth_client_secret}".encode()).decode()
    req = urllib.request.Request("https://api.bandwidth.com/api/v1/oauth2/token", data=b"grant_type=client_credentials",
                                 headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as answer:              # noqa: S310
        got = json.loads(answer.read().decode())
    _token.update(value=got["access_token"], until=time.time() + int(got.get("expires_in", 3600)) - 60)
    return _token["value"]


def _bandwidth(to: str, body: str) -> tuple[str, str | None, str | None]:
    """One text through Bandwidth: (status, its id, what went wrong). Accepted is not delivered: it
    means Bandwidth has it."""
    url = f"https://api.bandwidth.com/v1/build/accounts/{settings.bandwidth_account_id}/messages"
    data = json.dumps({"to": [to], "from": settings.bandwidth_from, "text": body,
                       "applicationId": settings.bandwidth_application_id}).encode()
    try:
        req = urllib.request.Request(url, data=data, headers={"Authorization": f"Bearer {_bandwidth_token()}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as answer:          # noqa: S310
            return "sent", json.loads(answer.read().decode()).get("id"), None
    except urllib.error.HTTPError as e:
        if e.code == 401:
            _token["value"] = None
        try:
            said = json.loads(e.read().decode())
            return "failed", None, str(said.get("description") or said.get("errors") or e.code)
        except Exception:                                                     # noqa: BLE001
            return "failed", None, str(e)
    except Exception as e:                                                    # noqa: BLE001
        return "failed", None, str(e)


def _send(rid: str, to: str, body: str) -> None:
    if settings.bandwidth_client_id:
        status, twiliosid, error = _bandwidth(to, body)
        if status == "failed":
            log.warning("text to %s failed: %s", to, error)
        with engine.begin() as conn:
            run(conn, "UPDATE drivertexts SET status = :s, twiliosid = :sid, error = :e, sent = :now WHERE recordid = :r",
                s=status, sid=twiliosid, e=(error or "")[:400] or None, now=utcnow(), r=rid)
        return
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
