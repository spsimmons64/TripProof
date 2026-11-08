"""Notifications to the TripProofDriver app, through Firebase Cloud Messaging.

One path for both phones: the app registers with Firebase on Android and on iPhone alike (Apple's
service sits behind Firebase), so the server only ever talks to FCM's HTTP v1 API.

Credentials are a Firebase service account's JSON key file, kept on the server and named by
FCM_CREDENTIALS. Without it nothing is pushed and every driver is texted as before.

What a notification says is exactly what the text would have said: the trip's reference and its
time. Nothing about the passenger - a lock screen is not a private place either.
"""

import json
import logging
import time
import urllib.error
import urllib.request
from functools import lru_cache

import jwt

from app.config import settings

log = logging.getLogger(__name__)
TIMEOUT = 15
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
# What FCM says about a token that will never work again - the app was removed, or the phone reset.
GONE = ("UNREGISTERED", "NOT_FOUND")


@lru_cache(maxsize=1)
def _account() -> dict | None:
    path = settings.fcm_credentials
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            got = json.load(f)
        return got if got.get("private_key") and got.get("client_email") and got.get("project_id") else None
    except OSError as e:
        log.warning("push credentials unreadable: %s", e)
        return None


def can_push() -> bool:
    return _account() is not None


_token = {"value": None, "until": 0.0}


def _access_token() -> str:
    if _token["value"] and time.time() < _token["until"]:
        return _token["value"]
    acct = _account()
    now = int(time.time())
    uri = acct.get("token_uri") or "https://oauth2.googleapis.com/token"
    assertion = jwt.encode({"iss": acct["client_email"], "scope": SCOPE, "aud": uri, "iat": now, "exp": now + 3600},
                           acct["private_key"], algorithm="RS256")
    data = f"grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion={assertion}".encode()
    req = urllib.request.Request(uri, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as answer:              # noqa: S310
        got = json.loads(answer.read().decode())
    _token.update(value=got["access_token"], until=time.time() + int(got.get("expires_in", 3600)) - 60)
    return _token["value"]


def message(token: str, body: str, data: dict) -> dict:
    """The FCM message for one notification - separate so the tests can read it."""
    return {"message": {
        "token": token,
        "notification": {"title": "TripProof", "body": body},
        # Every value a string: FCM refuses anything else in data.
        "data": {k: str(v) for k, v in data.items() if v is not None},
        # High priority so a phone dozing in a cradle wakes for it; the channel the app creates
        # for trip messages, which is allowed to make a sound.
        "android": {"priority": "HIGH", "notification": {"channel_id": "trips", "sound": "default"}},
        "apns": {"headers": {"apns-priority": "10"}, "payload": {"aps": {"sound": "default"}}},
    }}


def send(token: str, body: str, data: dict) -> tuple[str, str | None, str | None, bool]:
    """One notification: (status, its id, what went wrong, whether the token is gone for good).
    Sent is not delivered: it means Firebase has it."""
    url = f"https://fcm.googleapis.com/v1/projects/{_account()['project_id']}/messages:send"
    try:
        req = urllib.request.Request(url, data=json.dumps(message(token, body, data)).encode(),
                                     headers={"Authorization": f"Bearer {_access_token()}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as answer:          # noqa: S310
            return "sent", json.loads(answer.read().decode()).get("name"), None, False
    except urllib.error.HTTPError as e:
        if e.code == 401:
            _token["value"] = None
        try:
            said = json.loads(e.read().decode()).get("error", {})
        except Exception:                                                     # noqa: BLE001
            said = {}
        codes = [d.get("errorCode") for d in said.get("details", []) if isinstance(d, dict)]
        gone = e.code == 404 or any(c in GONE for c in codes)
        return "failed", None, str(said.get("message") or e.code), gone
    except Exception as e:                                                    # noqa: BLE001
        return "failed", None, str(e), False
